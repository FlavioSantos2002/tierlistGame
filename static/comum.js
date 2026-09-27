// Funções usadas pelas telas do jogador e do admin.
// Escrito em JavaScript "clássico" (var, function, sem async/await nem =>)
// para funcionar também nos navegadores de celulares antigos.
var TierList = (function () {
  "use strict";

  var INTERVALO_MS = 2000;      // polling a cada 2 s
  var TEMPO_LIMITE_MS = 8000;   // pedido sem resposta em 8 s conta como "sem conexão"

  // ----- Criação de elementos (sempre com textContent: nada vira HTML) -----

  function el(tag, classe, texto) {
    var elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = texto;
    return elemento;
  }

  // Preto ou branco: o que tiver mais contraste com a cor de fundo da faixa.
  function corDoTexto(hex) {
    var r = parseInt(hex.substr(1, 2), 16);
    var g = parseInt(hex.substr(3, 2), 16);
    var b = parseInt(hex.substr(5, 2), 16);
    return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#000000" : "#ffffff";
  }

  function pintarFaixa(elemento, faixa) {
    elemento.style.backgroundColor = faixa.cor;
    elemento.style.color = corDoTexto(faixa.cor);
  }

  function imagem(item, classe) {
    var img = el("img", classe);
    img.alt = item.nome;
    img.referrerPolicy = "no-referrer";
    // Se a imagem não carregar, o nome do item (alt) continua aparecendo.
    img.addEventListener("error", function () { img.classList.add("sem-imagem"); });
    img.src = item.imagem;
    return img;
  }

  function miniatura(item) {
    var figura = el("figure", item.novo ? "miniatura-tier novo" : "miniatura-tier");
    figura.appendChild(imagem(item));
    figura.appendChild(el("figcaption", null, item.nome));
    return figura;
  }

  // ----- Tier list e distribuição de votos -----

  function desenharTierList(container, estado) {
    container.textContent = "";
    var tabela = el("div", "tier-list");
    estado.faixas.forEach(function (faixa, indice) {
      var linha = el("div", "tier-linha");
      var rotulo = el("div", "tier-rotulo", faixa.rotulo);
      pintarFaixa(rotulo, faixa);
      if (faixa.descricao) rotulo.title = faixa.descricao;
      var itens = el("div", "tier-itens");
      estado.tier_list[indice].forEach(function (item) {
        itens.appendChild(miniatura(item));
      });
      linha.appendChild(rotulo);
      linha.appendChild(itens);
      tabela.appendChild(linha);
    });
    container.appendChild(tabela);

    if (estado.pulados.length > 0) {
      var area = el("div", "pulados");
      area.appendChild(el("h3", null, "Itens pulados"));
      var itens = el("div", "tier-itens");
      estado.pulados.forEach(function (item) { itens.appendChild(miniatura(item)); });
      area.appendChild(itens);
      container.appendChild(area);
    }
  }

  // Onde o item da rodada atual ficou: a faixa, ou null se foi pulado.
  function faixaDoItemNovo(estado) {
    for (var i = 0; i < estado.tier_list.length; i++) {
      for (var j = 0; j < estado.tier_list[i].length; j++) {
        if (estado.tier_list[i][j].novo) return estado.faixas[i];
      }
    }
    return null;
  }

  // Barras com a quantidade de votos por faixa (anônimo: só números).
  function desenharDistribuicao(container, estado) {
    container.textContent = "";
    var maior = Math.max.apply(null, estado.distribuicao.concat([1]));
    estado.faixas.forEach(function (faixa, indice) {
      var quantidade = estado.distribuicao[indice];
      var linha = el("div", "dist-linha");
      var rotulo = el("span", "dist-rotulo", faixa.rotulo);
      pintarFaixa(rotulo, faixa);
      var barra = el("span", "dist-barra");
      var preenchido = el("span", "dist-preenchido");
      preenchido.style.width = (quantidade / maior) * 100 + "%";
      preenchido.style.backgroundColor = faixa.cor;
      barra.appendChild(preenchido);
      linha.appendChild(rotulo);
      linha.appendChild(barra);
      linha.appendChild(el("span", "dist-numero", String(quantidade)));
      container.appendChild(linha);
    });
    if (estado.abstencoes > 0) {
      var texto = estado.abstencoes === 1 ? "1 pessoa pulou" : estado.abstencoes + " pessoas pularam";
      container.appendChild(el("p", "suave", texto));
    }
  }

  // "Faltam X de Y online (N offline)"
  function textoPresenca(presenca) {
    var texto = "Faltam " + presenca.faltam + " de " + presenca.online + " online";
    if (presenca.offline > 0) texto += " (" + presenca.offline + " offline)";
    return texto;
  }

  // ----- Conversa com o servidor -----

  // Resolve com o resultado de `promessa`, ou rejeita se ela passar de `ms`.
  // Uma resposta que chegue depois disso é ignorada (a promessa já terminou).
  function comTempoLimite(promessa, ms, aoEsgotar) {
    return new Promise(function (resolver, rejeitar) {
      var timer = setTimeout(function () {
        aoEsgotar();
        rejeitar(new Error("tempo esgotado"));
      }, ms);
      promessa.then(
        function (valor) { clearTimeout(timer); resolver(valor); },
        function (erro) { clearTimeout(timer); rejeitar(erro); }
      );
    });
  }

  // Cria o "sincronizador" de uma tela:
  // - consulta opcoes.urlEstado a cada 2 s;
  // - chama opcoes.desenhar(estado) só quando a versão do estado muda
  //   (e sempre depois de uma ação);
  // - chama opcoes.aoResponder(status, dados) em toda resposta (status 0 = sem conexão).
  //
  // FILA ÚNICA: o navegador só manda um pedido depois que o anterior terminou
  // (respondeu, falhou ou esgotou o tempo). Uma ação espera o polling em
  // andamento e passa na frente do próximo. Assim, entre os pedidos que ainda
  // esperamos, as respostas são aplicadas na ordem em que foram enviados.
  //
  // Atenção: um pedido que esgotou o tempo pode continuar na rede e chegar ao
  // servidor depois do seguinte. Por isso a resposta dele é ignorada aqui, e o
  // servidor recusa um voto antigo pela revisão (ver jogo._conferir_revisao).
  function criarSincronizador(opcoes) {
    var ocupado = false;        // já existe um pedido a caminho?
    var acaoNaFila = null;      // ação esperando a vez: {url, corpo, avisar}
    var pollingNaFila = false;  // consulta de estado esperando a vez
    var versao = null;
    var parado = false;

    function tratar(status, dados, sempreDesenhar) {
      if (parado) return;
      var estado = status === 200 ? dados : (dados && dados.estado);
      if (estado && (sempreDesenhar || estado.versao !== versao)) {
        versao = estado.versao;
        opcoes.desenhar(estado);
      }
      opcoes.aoResponder(status, dados);
    }

    // Envia um pedido e devolve uma promessa que nunca falha:
    // sem conexão ou tempo esgotado viram {status: 0}.
    function enviar(metodo, url, corpo) {
      ocupado = true;
      var controle = typeof AbortController === "function" ? new AbortController() : null;
      var config = { method: metodo, credentials: "same-origin", cache: "no-store", headers: {} };
      if (controle) config.signal = controle.signal;
      if (corpo) {
        config.headers["Content-Type"] = "application/json";
        config.body = JSON.stringify(corpo);
      }
      // O tempo limite vale para o pedido inteiro, inclusive a leitura do corpo.
      var pedido = fetch(url, config).then(function (resposta) {
        return resposta.json().then(
          function (dados) { return { status: resposta.status, dados: dados }; },
          function () { return { status: resposta.status, dados: null }; }
        );
      });
      return comTempoLimite(pedido, TEMPO_LIMITE_MS, function () {
        if (controle) controle.abort();
      })
        .then(null, function () { return { status: 0, dados: null }; })
        .then(function (resultado) {
          ocupado = false;
          try {
            tratar(resultado.status, resultado.dados, metodo === "POST");
          } catch (erro) {
            // Um erro ao desenhar a tela não pode parar o polling.
            if (window.console) console.error(erro);
          }
          proximo();
          return resultado;
        });
    }

    // Manda o próximo pedido da fila, se não houver outro no ar.
    function proximo() {
      if (ocupado) return;
      if (parado) {
        // A tela parou (ex.: partida apagada): a ação que esperava não será enviada.
        if (acaoNaFila) {
          var cancelada = acaoNaFila;
          acaoNaFila = null;
          cancelada.avisar({ status: 0, dados: null });
        }
        return;
      }
      if (acaoNaFila) {
        var acao = acaoNaFila;
        acaoNaFila = null;
        enviar("POST", acao.url, acao.corpo).then(acao.avisar);
      } else if (pollingNaFila) {
        pollingNaFila = false;
        enviar("GET", opcoes.urlEstado).then(function () {
          if (!parado) {
            setTimeout(function () { pollingNaFila = true; proximo(); }, INTERVALO_MS);
          }
        });
      }
    }

    return {
      iniciar: function () { pollingNaFila = true; proximo(); },
      // Ação (POST): entra na fila e a promessa resolve quando ela terminar
      // (com sucesso, erro ou sem conexão). POST nunca é reenviado sozinho:
      // ele pode ter sido aplicado (ou ainda ser) mesmo sem a resposta chegar.
      acao: function (url, corpo) {
        if (parado || acaoNaFila) return Promise.resolve({ status: 0, dados: null });
        return new Promise(function (avisar) {
          acaoNaFila = { url: url, corpo: corpo, avisar: avisar };
          proximo();
        });
      },
      parar: function () { parado = true; proximo(); }
    };
  }

  return {
    el: el,
    imagem: imagem,
    pintarFaixa: pintarFaixa,
    desenharTierList: desenharTierList,
    desenharDistribuicao: desenharDistribuicao,
    faixaDoItemNovo: faixaDoItemNovo,
    textoPresenca: textoPresenca,
    criarSincronizador: criarSincronizador
  };
})();

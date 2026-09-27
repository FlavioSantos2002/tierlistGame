// Tela do jogador: espera, votação, resultado e encerrada.
// O servidor manda o estado a cada 2 s; a tela só é redesenhada quando ele muda.
(function () {
  "use strict";

  var el = TierList.el;
  var raiz = document.getElementById("jogo");
  var aviso = document.getElementById("aviso");
  var urls = {
    estado: raiz.getAttribute("data-url-estado"),
    votar: raiz.getAttribute("data-url-votar"),
    pular: raiz.getAttribute("data-url-pular"),
    continuar: raiz.getAttribute("data-url-continuar")
  };

  var estadoAtual = null;
  // Ação a caminho: os botões ficam desativados até ELA terminar, mesmo que a
  // tela seja redesenhada no meio (ex.: outro jogador votou). Só o fim da
  // ação libera, então dois votos nunca saem ao mesmo tempo.
  var acaoEmAndamento = false;
  // Partida apagada: estado final. Nada mais redesenha a tela nem envia ações.
  var apagada = false;
  var timerAviso = null;
  var avisoTemporario = false;  // avisos de ação somem sozinhos; o de conexão, não

  // ----- Avisos (sem conexão, ação recusada) -----

  function mostrarAviso(texto, segundos) {
    aviso.textContent = texto;
    aviso.hidden = false;
    clearTimeout(timerAviso);
    avisoTemporario = Boolean(segundos);
    if (segundos) {
      timerAviso = setTimeout(esconderAviso, segundos * 1000);
    }
  }

  function esconderAviso() {
    clearTimeout(timerAviso);
    avisoTemporario = false;
    aviso.hidden = true;
  }

  // ----- Ações -----

  function desativarBotoes() {
    // Array.prototype.forEach.call: funciona até em navegadores sem NodeList.forEach.
    Array.prototype.forEach.call(raiz.querySelectorAll("button"), function (botao) {
      botao.disabled = true;
    });
  }

  function agir(tipo, corpo) {
    if (acaoEmAndamento || apagada || !estadoAtual) return;
    acaoEmAndamento = true;
    desativarBotoes();
    corpo.rodada = estadoAtual.rodada;
    // Votar e pular levam a revisão do voto que está na tela. Se o servidor já
    // tiver outra (um envio antigo chegou atrasado, por exemplo), ele recusa com
    // 409 e devolve o estado atual, em vez de trocar a escolha sem ninguém ver.
    if (tipo !== "continuar") corpo.revisao = estadoAtual.eu.revisao;
    sincronizador.acao(urls[tipo], corpo).then(function () {
      // A ação terminou (deu certo, foi recusada ou ficou sem conexão):
      // só agora os botões voltam, redesenhando com o estado mais recente.
      acaoEmAndamento = false;
      if (!apagada && estadoAtual) desenhar(estadoAtual);
    });
  }

  // ----- Telas -----

  function cabecalho(estado, subtitulo) {
    var bloco = el("div", "cabecalho-jogo");
    bloco.appendChild(el("p", "suave", estado.tema));
    bloco.appendChild(el("h1", null, subtitulo));
    return bloco;
  }

  function telaEspera(estado) {
    var tela = el("div", "cartao centro");
    tela.appendChild(el("h1", null, "Olá, " + estado.eu.nome + "!"));
    tela.appendChild(el("p", null, "Tema: " + estado.tema));
    tela.appendChild(el("p", "destaque", "Aguardando o início"));
    tela.appendChild(el("p", "suave", "Já entraram (" + estado.entraram.length + "):"));
    var lista = el("ul", "lista-nomes");
    estado.entraram.forEach(function (nome) { lista.appendChild(el("li", null, nome)); });
    tela.appendChild(lista);
    return tela;
  }

  function telaVotacao(estado) {
    var tela = el("div");
    tela.appendChild(cabecalho(estado, "Rodada " + estado.rodada + " de " + estado.total_rodadas));

    var item = el("figure", "item-atual");
    item.appendChild(TierList.imagem(estado.item));
    item.appendChild(el("figcaption", null, estado.item.nome));
    tela.appendChild(item);

    var eu = estado.eu;
    if (eu.voto !== null) {
      tela.appendChild(el("p", "centro",
        "Seu voto: " + estado.faixas[eu.voto].rotulo + ". Dá para trocar enquanto a rodada estiver aberta."));
    } else if (eu.pulou) {
      tela.appendChild(el("p", "centro", "Você pulou este item. Ainda dá para votar."));
    }

    var botoes = el("div", "botoes-faixa");
    estado.faixas.forEach(function (faixa, indice) {
      var botao = el("button", indice === eu.voto ? "botao-faixa escolhida" : "botao-faixa");
      botao.type = "button";
      TierList.pintarFaixa(botao, faixa);
      botao.appendChild(el("span", "botao-faixa-rotulo", faixa.rotulo));
      if (faixa.descricao) botao.appendChild(el("span", "botao-faixa-descricao", faixa.descricao));
      botao.addEventListener("click", function () { agir("votar", { faixa: indice }); });
      botoes.appendChild(botao);
    });
    tela.appendChild(botoes);

    // "Pular" só existe antes de votar (e some depois de pular).
    if (eu.voto === null && !eu.pulou) {
      var pular = el("button", "secundario largo", "Pular este item");
      pular.type = "button";
      pular.addEventListener("click", function () { agir("pular", {}); });
      tela.appendChild(pular);
    } else {
      tela.appendChild(el("p", "presenca", TierList.textoPresenca(estado.presenca)));
    }
    return tela;
  }

  function telaResultado(estado) {
    var tela = el("div");
    tela.appendChild(cabecalho(estado, "Resultado da rodada " + estado.rodada + " de " + estado.total_rodadas));

    var resumo = el("div", "resumo-item");
    resumo.appendChild(TierList.imagem(estado.item, "resumo-imagem"));
    var texto = el("div");
    texto.appendChild(el("p", "resumo-nome", estado.item.nome));
    var faixa = TierList.faixaDoItemNovo(estado);
    if (faixa) {
      var linha = el("p", null, "Ficou na faixa ");
      var etiqueta = el("span", "etiqueta", faixa.rotulo);
      TierList.pintarFaixa(etiqueta, faixa);
      linha.appendChild(etiqueta);
      texto.appendChild(linha);
    } else {
      texto.appendChild(el("p", null, "Ficou fora da tier list: nenhum voto recebido."));
    }
    resumo.appendChild(texto);
    tela.appendChild(resumo);

    var distribuicao = el("div", "distribuicao");
    TierList.desenharDistribuicao(distribuicao, estado);
    tela.appendChild(distribuicao);

    if (estado.eu.continuou) {
      tela.appendChild(el("p", "presenca", TierList.textoPresenca(estado.presenca)));
    } else {
      var continuar = el("button", "largo", "Continuar");
      continuar.type = "button";
      continuar.addEventListener("click", function () { agir("continuar", {}); });
      tela.appendChild(continuar);
    }

    tela.appendChild(el("h2", null, "Tier list do grupo"));
    var tier = el("div");
    TierList.desenharTierList(tier, estado);
    tela.appendChild(tier);
    return tela;
  }

  function telaEncerrada(estado) {
    var tela = el("div");
    tela.appendChild(cabecalho(estado, "Fim de jogo!"));
    tela.appendChild(el("p", null, "A tier list final do grupo:"));
    var tier = el("div");
    TierList.desenharTierList(tier, estado);
    tela.appendChild(tier);
    return tela;
  }

  // Mesmo texto da página jogador_sem_partida.html (link aberto depois de apagar).
  function telaApagada(mensagem) {
    var tela = el("div", "cartao centro");
    tela.appendChild(el("h1", null, mensagem || "Esta partida foi encerrada pelo admin"));
    tela.appendChild(el("p", null, "Se você acha que é engano, confira o link com quem te convidou."));
    return tela;
  }

  var TELAS = {
    espera: telaEspera,
    votacao: telaVotacao,
    resultado: telaResultado,
    encerrada: telaEncerrada
  };

  function desenhar(estado) {
    if (apagada) return;
    estadoAtual = estado;
    raiz.textContent = "";
    raiz.appendChild(TELAS[estado.estado](estado));
    if (acaoEmAndamento) desativarBotoes();
  }

  // ----- Respostas do servidor -----

  function aoResponder(status, dados) {
    if (status === 200) {
      // A conexão voltou: some o aviso de conexão (um aviso de ação some sozinho).
      if (!avisoTemporario) esconderAviso();
      return;
    }
    if (status === 0) {
      mostrarAviso("Sem conexão. Tentando de novo…");
    } else if (status === 404 && dados && dados.apagada) {
      apagada = true;
      acaoEmAndamento = false;
      sincronizador.parar();
      esconderAviso();
      raiz.textContent = "";
      raiz.appendChild(telaApagada(dados.mensagem));
    } else if (dados && dados.erro) {
      // Ex.: a rodada fechou enquanto o voto estava a caminho (409).
      mostrarAviso(dados.erro, 4);
    } else {
      mostrarAviso("Algo deu errado. Tentando de novo…");
    }
  }

  var sincronizador = TierList.criarSincronizador({
    urlEstado: urls.estado,
    desenhar: desenhar,
    aoResponder: aoResponder
  });
  sincronizador.iniciar();
})();

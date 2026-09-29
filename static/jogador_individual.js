// Tela do jogador no modo individual ("cada um no seu ritmo").
// - Preenchendo: uma imagem por vez, faixas + "Pular", "Voltar", progresso,
//   a tier list pessoal em formação (tocar num item para mudar) e "Finalizar".
// - Depois de finalizar (ou com a partida encerrada): a própria lista, a geral,
//   a compatibilidade, as listas de quem finalizou e quem ainda falta.
// Cada resposta é salva no servidor na hora: dá para fechar e continuar depois.
(function () {
  "use strict";

  var INTERVALO_MS = 5000;      // modo individual: consulta mais leve, a cada 5 s

  var el = TierList.el;
  var raiz = document.getElementById("jogo");
  var aviso = TierList.criarAviso(document.getElementById("aviso"));
  var urls = {
    estado: raiz.getAttribute("data-url-estado"),
    responder: raiz.getAttribute("data-url-responder"),
    finalizar: raiz.getAttribute("data-url-finalizar")
  };

  var estadoAtual = null;
  // Posição (0, 1, 2...) do item mostrado no topo, na ordem deste jogador.
  // Igual ao número de itens = tela de "tudo respondido". null = decidir no
  // próximo desenho (começa no primeiro item sem resposta).
  var posicao = null;
  // Mesmas travas da tela ao vivo: botões desativados até a ação terminar, e
  // partida apagada / jogador removido como estado final.
  var acaoEmAndamento = false;
  var fimDefinitivo = false;

  // ----- Ações -----

  // Durante o envio, nada muda de tela: os botões ficam desativados e as
  // miniaturas tocáveis também (o irPara recusa). Senão, a resposta chegando
  // desfaria a navegação feita no meio do envio.
  function desativarBotoes() {
    Array.prototype.forEach.call(raiz.querySelectorAll("button"), function (botao) {
      botao.disabled = true;
    });
    Array.prototype.forEach.call(raiz.querySelectorAll(".tocavel"), function (miniatura) {
      miniatura.setAttribute("aria-disabled", "true");
      miniatura.tabIndex = -1;
    });
  }

  // Envia uma ação; `depoisDeDarCerto` roda só se o servidor aceitou (200).
  function agir(url, corpo, depoisDeDarCerto) {
    if (acaoEmAndamento || fimDefinitivo || !estadoAtual) return;
    acaoEmAndamento = true;
    desativarBotoes();
    sincronizador.acao(url, corpo).then(function (resultado) {
      acaoEmAndamento = false;
      if (resultado.status === 200 && depoisDeDarCerto) depoisDeDarCerto();
      if (!fimDefinitivo && estadoAtual) desenhar(estadoAtual);
    });
  }

  // faixa = índice da faixa, ou null para "pular". Depois, vai para o próximo.
  function responder(item, faixa) {
    var daqui = posicao;
    agir(urls.responder, { item: item.id, faixa: faixa, revisao: item.revisao }, function () {
      posicao = daqui + 1;
    });
  }

  function finalizar() {
    if (!window.confirm("Depois de finalizar, não dá para mudar as respostas. Finalizar agora?")) return;
    agir(urls.finalizar, {});
  }

  function irPara(novaPosicao) {
    if (acaoEmAndamento || fimDefinitivo) return;
    posicao = novaPosicao;
    desenhar(estadoAtual);
    if (window.scrollTo) window.scrollTo(0, 0);
  }

  // ----- Preenchimento -----

  function primeiroSemResposta(itens) {
    for (var i = 0; i < itens.length; i++) {
      if (!itens[i].respondido) return i;
    }
    return itens.length;
  }

  // A tier list pessoal em formação, só com os itens já respondidos.
  function minhaLista(estado) {
    var tier = estado.faixas.map(function () { return []; });
    var pulados = [];
    estado.itens.forEach(function (item) {
      if (!item.respondido) return;
      var dados = { id: item.id, nome: item.nome, imagem: item.imagem, novo: false };
      if (item.faixa === null) pulados.push(dados);
      else tier[item.faixa].push(dados);
    });
    return { faixas: estado.faixas, tier_list: tier, pulados: pulados };
  }

  function barraDeProgresso(respondidos, total) {
    var bloco = el("div", "progresso");
    var barra = el("div", "progresso-barra");
    var preenchido = el("div", "progresso-preenchido");
    preenchido.style.width = (total ? respondidos / total * 100 : 0) + "%";
    barra.appendChild(preenchido);
    bloco.appendChild(barra);
    bloco.appendChild(el("p", "progresso-texto", respondidos + " de " + total));
    return bloco;
  }

  function cartaoDoItem(estado, item) {
    var cartao = el("div", "cartao-item");
    cartao.appendChild(el("p", "suave centro", "Item " + (posicao + 1) + " de " + estado.itens.length));
    var figura = el("figure", "item-atual");
    figura.appendChild(TierList.imagem(item));
    figura.appendChild(el("figcaption", null, item.nome));
    cartao.appendChild(figura);

    if (item.respondido) {
      cartao.appendChild(el("p", "centro", item.faixa === null
        ? "Você pulou este item. Pode escolher uma faixa se quiser."
        : "Sua resposta: " + estado.faixas[item.faixa].rotulo + ". Pode trocar."));
    }

    var botoes = el("div", "botoes-faixa");
    estado.faixas.forEach(function (faixa, indice) {
      var escolhida = item.respondido && item.faixa === indice;
      var botao = el("button", escolhida ? "botao-faixa escolhida" : "botao-faixa");
      botao.type = "button";
      TierList.pintarFaixa(botao, faixa);
      botao.appendChild(el("span", "botao-faixa-rotulo", faixa.rotulo));
      if (faixa.descricao) botao.appendChild(el("span", "botao-faixa-descricao", faixa.descricao));
      botao.addEventListener("click", function () { responder(item, indice); });
      botoes.appendChild(botao);
    });
    cartao.appendChild(botoes);

    var navegacao = el("div", "navegacao");
    var voltar = el("button", "secundario", "Voltar");
    voltar.type = "button";
    voltar.disabled = posicao === 0;
    voltar.addEventListener("click", function () { irPara(posicao - 1); });
    var pular = el("button", item.respondido && item.faixa === null ? "secundario escolhida" : "secundario",
      "Pular");
    pular.type = "button";
    pular.addEventListener("click", function () { responder(item, null); });
    navegacao.appendChild(voltar);
    navegacao.appendChild(pular);
    cartao.appendChild(navegacao);
    return cartao;
  }

  function cartaoDeRevisao(estado) {
    var faltam = estado.itens.length - estado.eu.respondidos;
    var cartao = el("div", "cartao centro");
    if (faltam === 0) {
      cartao.appendChild(el("p", "destaque", "Todos os itens têm resposta."));
      cartao.appendChild(el("p", null, "Confira a sua lista abaixo (toque num item para mudar) e finalize."));
    } else {
      cartao.appendChild(el("p", "destaque", "Ainda falta responder " + faltam + (faltam === 1 ? " item." : " itens.")));
      var ir = el("button", null, "Responder o que falta");
      ir.type = "button";
      ir.addEventListener("click", function () { irPara(primeiroSemResposta(estado.itens)); });
      cartao.appendChild(ir);
    }
    var voltar = el("button", "secundario", "Voltar");
    voltar.type = "button";
    voltar.addEventListener("click", function () { irPara(estado.itens.length - 1); });
    cartao.appendChild(voltar);
    return cartao;
  }

  function telaPreenchimento(estado) {
    var tela = el("div");
    var total = estado.itens.length;
    if (posicao === null) posicao = primeiroSemResposta(estado.itens);
    if (posicao > total) posicao = total;

    tela.appendChild(el("p", "suave centro", estado.tema));
    tela.appendChild(el("h1", "centro", "Monte a sua tier list"));
    tela.appendChild(barraDeProgresso(estado.eu.respondidos, total));
    tela.appendChild(posicao < total ? cartaoDoItem(estado, estado.itens[posicao]) : cartaoDeRevisao(estado));

    // "Finalizar" só funciona com tudo respondido.
    var finalizarBotao = el("button", "largo", "Finalizar");
    finalizarBotao.type = "button";
    finalizarBotao.id = "botao-finalizar";
    finalizarBotao.disabled = estado.eu.respondidos < total;
    finalizarBotao.addEventListener("click", finalizar);
    tela.appendChild(finalizarBotao);
    if (estado.eu.respondidos < total) {
      tela.appendChild(el("p", "suave centro", "O botão Finalizar libera quando todos os itens tiverem resposta."));
    }

    tela.appendChild(el("h2", null, "Sua tier list até agora"));
    if (estado.eu.respondidos === 0) {
      tela.appendChild(el("p", "suave", "Ela vai aparecendo aqui conforme você responde."));
    } else {
      var lista = el("div");
      TierList.desenharTierList(lista, minhaLista(estado), function (item) {
        for (var i = 0; i < estado.itens.length; i++) {
          if (estado.itens[i].id === item.id) { irPara(i); return; }
        }
      });
      tela.appendChild(lista);
    }
    return tela;
  }

  // ----- Resultado (depois de finalizar, ou partida encerrada) -----

  function tierList(titulo, lista, faixas) {
    var bloco = el("section", "bloco-lista");
    bloco.appendChild(el("h2", null, titulo));
    var container = el("div");
    TierList.desenharTierList(container, {
      faixas: faixas, tier_list: lista.tier_list, pulados: lista.pulados
    });
    bloco.appendChild(container);
    return bloco;
  }

  function telaResultado(estado) {
    var resultado = estado.resultado;
    var tela = el("div");
    tela.appendChild(el("p", "suave centro", estado.tema));
    tela.appendChild(el("h1", "centro", estado.estado === "encerrada" ? "Resultado final" : "Você finalizou!"));

    if (estado.eu.finalizado) {
      var compat = el("div", "cartao centro compatibilidade");
      compat.appendChild(el("p", null, "Sua compatibilidade com a tier list geral"));
      compat.appendChild(el("p", "compatibilidade-numero",
        resultado.compatibilidade === null ? "—" : resultado.compatibilidade + "%"));
      tela.appendChild(compat);
    } else {
      tela.appendChild(el("p", "cartao centro",
        "A partida foi encerrada antes de você finalizar: suas respostas ficaram de fora do resultado."));
    }

    if (estado.estado === "aberta" && resultado.faltam.length > 0) {
      tela.appendChild(el("p", "presenca", "Faltam: " + resultado.faltam.join(", ")));
      tela.appendChild(el("p", "suave centro", "A tier list geral muda conforme mais gente finaliza."));
    }

    if (resultado.geral) {
      tela.appendChild(tierList("Tier list geral", resultado.geral, estado.faixas));
    } else {
      tela.appendChild(el("h2", null, "Tier list geral"));
      tela.appendChild(el("p", "suave", "Ninguém finalizou, então não há tier list geral."));
    }
    if (resultado.minha) {
      tela.appendChild(tierList("A sua tier list", resultado.minha, estado.faixas));
    }
    resultado.outros.forEach(function (outro) {
      tela.appendChild(tierList("Tier list de " + outro.nome, outro, estado.faixas));
    });
    return tela;
  }

  function telaFinal(titulo, texto) {
    var tela = el("div", "cartao centro");
    tela.appendChild(el("h1", null, titulo));
    tela.appendChild(el("p", null, texto));
    return tela;
  }

  function desenhar(estado) {
    if (fimDefinitivo) return;
    estadoAtual = estado;
    raiz.textContent = "";
    raiz.appendChild(estado.itens ? telaPreenchimento(estado) : telaResultado(estado));
    if (acaoEmAndamento) desativarBotoes();
  }

  // ----- Respostas do servidor -----

  function aoResponder(status, dados) {
    if (status === 200) {
      aviso.esconderSeNaoTemporario();
      return;
    }
    if (status === 0) {
      aviso.mostrar("Sem conexão. Suas respostas já salvas continuam salvas. Tentando de novo…");
    } else if ((status === 404 && dados && dados.apagada) || (status === 403 && dados && dados.removido)) {
      fimDefinitivo = true;
      acaoEmAndamento = false;
      sincronizador.parar();
      aviso.esconder();
      raiz.textContent = "";
      if (dados.removido) {
        raiz.appendChild(telaFinal("Você foi removido desta partida",
          "Se você acha que é engano, fale com quem te convidou."));
      } else {
        raiz.appendChild(telaFinal("Esta partida foi encerrada pelo admin",
          "Se você acha que é engano, confira o link com quem te convidou."));
      }
    } else if (dados && dados.erro) {
      aviso.mostrar(dados.erro, 4);
    } else {
      aviso.mostrar("Algo deu errado. Tentando de novo…");
    }
  }

  var sincronizador = TierList.criarSincronizador({
    urlEstado: urls.estado,
    intervaloMs: INTERVALO_MS,
    desenhar: desenhar,
    aoResponder: aoResponder
  });
  sincronizador.iniciar();
})();

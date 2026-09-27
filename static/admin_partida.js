// Tela da partida (admin): botão "Copiar" dos links e estado ao vivo.
(function () {
  "use strict";

  var el = TierList.el;

  // ----- Copiar links -----

  function copiarTexto(campo) {
    // A API moderna só funciona em HTTPS (o túnel) ou localhost.
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(campo.value);
    }
    // Plano B para HTTP comum: seleciona o texto e usa o comando antigo.
    campo.select();
    var deuCerto = document.execCommand("copy");
    return deuCerto ? Promise.resolve() : Promise.reject(new Error("falhou"));
  }

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".copiar");
    if (!botao) return;
    var campo = botao.parentElement.querySelector(".link");
    copiarTexto(campo).then(
      function () { botao.textContent = "Copiado!"; },
      function () { campo.select(); botao.textContent = "Copie à mão"; }
    ).then(function () {
      setTimeout(function () { botao.textContent = "Copiar"; }, 1500);
    });
  });

  // ----- Estado ao vivo -----

  var secao = document.getElementById("ao-vivo");
  var nomesEstados = JSON.parse(secao.getAttribute("data-nomes-estados"));
  var aviso = document.getElementById("aviso");
  var campos = {
    estado: document.getElementById("vivo-estado"),
    rodada: document.getElementById("vivo-rodada"),
    presenca: document.getElementById("vivo-presenca"),
    jogadores: document.getElementById("vivo-jogadores"),
    item: document.getElementById("vivo-item"),
    itemTitulo: document.getElementById("vivo-item-titulo"),
    itemImagem: document.getElementById("vivo-item-imagem"),
    itemNome: document.getElementById("vivo-item-nome"),
    distribuicao: document.getElementById("vivo-distribuicao"),
    tier: document.getElementById("vivo-tier"),
    formIniciar: document.getElementById("form-iniciar"),
    formForcar: document.getElementById("form-forcar"),
    forcarEstado: document.getElementById("forcar-estado"),
    forcarRodada: document.getElementById("forcar-rodada")
  };

  // O que cada jogador já fez nesta fase, em palavras.
  function situacaoDoJogador(jogador, estado) {
    if (!jogador.entrou) return "ainda não abriu o link";
    if (estado === "votacao") {
      if (jogador.acao === "votou") return "votou";
      if (jogador.acao === "pulou") return "pulou";
      return "ainda não votou";
    }
    if (estado === "resultado") {
      return jogador.acao === "continuou" ? "continuou" : "ainda não continuou";
    }
    return "entrou";
  }

  function desenharJogadores(estado) {
    campos.jogadores.textContent = "";
    estado.jogadores.forEach(function (jogador) {
      var classe = jogador.online ? "online" : (jogador.entrou ? "offline" : "nunca");
      var linha = el("li", "jogador-" + classe);
      linha.appendChild(el("span", "bolinha", ""));
      linha.appendChild(el("span", "jogador-nome", jogador.nome));
      var texto = situacaoDoJogador(jogador, estado.estado);
      if (jogador.entrou && !jogador.online) texto += " · offline";
      linha.appendChild(el("span", "suave", texto));
      campos.jogadores.appendChild(linha);
    });
  }

  function desenhar(estado) {
    campos.estado.textContent = nomesEstados[estado.estado] || estado.estado;
    campos.rodada.textContent = estado.rodada;

    // Botões: "Iniciar" só na espera; "Forçar avanço" na votação e no resultado,
    // sempre com a fase que está na tela.
    campos.formIniciar.hidden = estado.estado !== "espera";
    campos.formForcar.hidden = !(estado.estado === "votacao" || estado.estado === "resultado");
    campos.forcarEstado.value = estado.estado;
    campos.forcarRodada.value = estado.rodada;

    var emJogo = estado.estado === "votacao" || estado.estado === "resultado";
    campos.presenca.textContent = emJogo
      ? TierList.textoPresenca(estado.presenca)
      : estado.presenca.online + " online, " + estado.presenca.offline + " offline";
    desenharJogadores(estado);

    campos.item.hidden = !emJogo;
    if (emJogo) {
      campos.itemTitulo.textContent = estado.estado === "votacao"
        ? "Em votação" : "Resultado deste item";
      if (campos.itemImagem.getAttribute("src") !== estado.item.imagem) {
        campos.itemImagem.src = estado.item.imagem;
      }
      campos.itemImagem.alt = estado.item.nome;
      campos.itemNome.textContent = estado.item.nome;
      if (estado.estado === "resultado") {
        TierList.desenharDistribuicao(campos.distribuicao, estado);
      } else {
        campos.distribuicao.textContent = "";   // votos só aparecem depois de fechar
      }
    }

    TierList.desenharTierList(campos.tier, estado);
  }

  function mostrarAviso(texto) {
    aviso.textContent = texto;
    aviso.hidden = false;
  }

  function aoResponder(status, dados) {
    if (status === 200) {
      aviso.hidden = true;
    } else if (status === 0) {
      mostrarAviso("Sem conexão com o servidor. Tentando de novo…");
    } else if (status === 401) {
      sincronizador.parar();
      mostrarAviso("Sua sessão expirou. Recarregue a página e entre de novo.");
    } else if (status === 404) {
      sincronizador.parar();
      mostrarAviso("Esta partida foi apagada.");
    } else {
      mostrarAviso("Algo deu errado ao atualizar. Tentando de novo…");
    }
  }

  var sincronizador = TierList.criarSincronizador({
    urlEstado: secao.getAttribute("data-url-estado"),
    desenhar: desenhar,
    aoResponder: aoResponder
  });
  sincronizador.iniciar();
})();

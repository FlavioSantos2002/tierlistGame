// Tela da partida ao vivo (admin): estado ao vivo, "Iniciar", "Forçar avanço"
// e "Remover". Copiar links e o botão "Remover" vêm do admin_comum.js.
(function () {
  "use strict";

  var el = TierList.el;
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
    forcarRodada: document.getElementById("forcar-rodada"),
    forcarTexto: document.getElementById("forcar-texto")
  };

  // Texto do botão "forçar" e da confirmação, conforme a fase que está na tela
  // (os mesmos do template admin_partida.html). Fechar a votação e sair do
  // resultado são coisas diferentes: o botão diz qual vai acontecer.
  function textosDoForcar(estado) {
    var n = estado.rodada;
    if (estado.estado === "votacao") {
      return {
        botao: "Fechar a votação agora",
        confirmacao: "Fechar a votação da rodada " + n + " agora? Quem ainda não votou fica de fora. " +
          "Se ninguém tiver votado, o item vai para os pulados."
      };
    }
    if (n < estado.total_rodadas) {
      return {
        botao: "Ir para a próxima rodada",
        confirmacao: "Sair do resultado da rodada " + n + " e abrir a votação da rodada " + (n + 1) + "?"
      };
    }
    return {
      botao: "Encerrar a partida",
      confirmacao: "Sair do resultado da última rodada e encerrar a partida?"
    };
  }

  // O que cada jogador já fez nesta fase, em palavras.
  function situacaoDoJogador(jogador, estado) {
    if (jogador.removido) return "removido";
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
      var classe = jogador.removido ? "removido"
        : jogador.online ? "online" : (jogador.entrou ? "offline" : "nunca");
      var linha = el("li", "jogador-" + classe);
      linha.appendChild(el("span", "bolinha", ""));
      linha.appendChild(el("span", "jogador-nome", jogador.nome));
      var texto = situacaoDoJogador(jogador, estado.estado);
      if (!jogador.removido && jogador.entrou && !jogador.online) texto += " · offline";
      linha.appendChild(el("span", "suave", texto));
      // Depois que a partida termina, ninguém mais é removido (decisão do dono).
      if (!jogador.removido && estado.estado !== "encerrada") {
        linha.appendChild(Admin.botaoRemover(jogador));
      }
      campos.jogadores.appendChild(linha);
    });
  }

  function desenhar(estado) {
    campos.estado.textContent = Admin.nomesEstados[estado.estado] || estado.estado;
    campos.rodada.textContent = estado.rodada;

    // Botões: "Iniciar" só na espera; "Forçar avanço" na votação e no resultado,
    // sempre com a fase que está na tela.
    campos.formIniciar.hidden = estado.estado !== "espera";
    campos.formForcar.hidden = !(estado.estado === "votacao" || estado.estado === "resultado");
    campos.forcarEstado.value = estado.estado;
    campos.forcarRodada.value = estado.rodada;
    if (!campos.formForcar.hidden) {
      var textos = textosDoForcar(estado);
      campos.forcarTexto.textContent = textos.botao;
      campos.formForcar.setAttribute("data-confirmacao", textos.confirmacao);
    }

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

  Admin.criarSincronizador(desenhar).iniciar();
})();

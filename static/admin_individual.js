// Tela da partida no modo individual (admin): progresso de cada jogador,
// "Encerrar e revelar", "Remover", a tier list geral (só quem finalizou) e a
// lista de cada jogador (o admin pode ver todas, inclusive as parciais).
(function () {
  "use strict";

  var INTERVALO_MS = 5000;      // mesmo ritmo das telas dos jogadores neste modo

  var el = TierList.el;
  var campos = {
    estado: document.getElementById("vivo-estado"),
    jogadores: document.getElementById("vivo-jogadores"),
    tier: document.getElementById("vivo-tier"),
    listas: document.getElementById("vivo-listas"),
    formEncerrar: document.getElementById("form-encerrar")
  };

  // "Ana: 7 de 12", "Pedro: finalizou", "Bia: removida"...
  function progresso(jogador, total) {
    if (jogador.removido) return "removido";
    if (jogador.finalizado) return "finalizou";
    if (!jogador.entrou && jogador.respondidos === 0) return "ainda não abriu o link";
    return jogador.respondidos + " de " + total;
  }

  function desenharJogadores(estado) {
    campos.jogadores.textContent = "";
    estado.jogadores.forEach(function (jogador) {
      var classe = jogador.removido ? "removido" : (jogador.finalizado ? "online" : "nunca");
      var linha = el("li", "jogador-" + classe);
      linha.appendChild(el("span", "bolinha", ""));
      linha.appendChild(el("span", "jogador-nome", jogador.nome + ":"));
      linha.appendChild(el("span", "suave", progresso(jogador, estado.total_itens)));
      // Depois que a partida termina, ninguém mais é removido (decisão do dono).
      if (!jogador.removido && estado.estado !== "encerrada") {
        linha.appendChild(Admin.botaoRemover(jogador));
      }
      campos.jogadores.appendChild(linha);
    });
  }

  function lista(container, dados, faixas) {
    TierList.desenharTierList(container, {
      faixas: faixas, tier_list: dados.tier_list, pulados: dados.pulados
    });
  }

  function desenharListas(estado) {
    campos.listas.textContent = "";
    var algum = false;
    estado.jogadores.forEach(function (jogador) {
      if (!jogador.lista) return;          // removidos não aparecem
      algum = true;
      var bloco = el("details", "lista-jogador");
      bloco.setAttribute("data-jogador", jogador.id);
      var resumo = el("summary", null, jogador.nome + " (" + progresso(jogador, estado.total_itens) + ")");
      bloco.appendChild(resumo);
      var container = el("div");
      if (jogador.respondidos === 0) {
        container.appendChild(el("p", "suave", "Ainda sem respostas."));
      } else {
        lista(container, jogador.lista, estado.faixas);
      }
      bloco.appendChild(container);
      campos.listas.appendChild(bloco);
    });
    if (!algum) campos.listas.appendChild(el("p", "suave", "Nenhum jogador ativo."));
  }

  function desenhar(estado) {
    campos.estado.textContent = Admin.nomesEstados[estado.estado] || estado.estado;
    campos.formEncerrar.hidden = estado.estado !== "aberta";

    // A confirmação avisa quando ninguém finalizou (o resultado sai vazio).
    var finalizaram = estado.jogadores.filter(function (j) { return j.finalizado && !j.removido; }).length;
    campos.formEncerrar.setAttribute("data-confirmacao", finalizaram === 0
      ? "Ninguém finalizou ainda: o resultado ficará vazio. Encerrar e revelar mesmo assim?"
      : "Encerrar a partida e revelar os resultados? Quem não finalizou fica de fora.");

    desenharJogadores(estado);
    if (estado.geral) {
      lista(campos.tier, estado.geral, estado.faixas);
    } else {
      campos.tier.textContent = "";
      campos.tier.appendChild(el("p", "suave", "Ninguém finalizou ainda."));
    }
    // Manter abertas as listas que o admin tinha aberto antes do redesenho.
    var abertos = {};
    Array.prototype.forEach.call(campos.listas.querySelectorAll("details[open]"), function (d) {
      abertos[d.getAttribute("data-jogador")] = true;
    });
    desenharListas(estado);
    Array.prototype.forEach.call(campos.listas.querySelectorAll("details"), function (d) {
      if (abertos[d.getAttribute("data-jogador")]) d.open = true;
    });
  }

  Admin.criarSincronizador(desenhar, INTERVALO_MS).iniciar();
})();

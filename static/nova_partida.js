// Tela "Nova partida": prévia das imagens do tema escolhido e faixas dinâmicas.
// As imagens são testadas aqui, no navegador do admin; o servidor nunca as baixa.
(function () {
  "use strict";

  var RODADAS_PADRAO = 12;

  var temas = JSON.parse(document.getElementById("dados-temas").textContent);
  var seletor = document.getElementById("tema");
  var previa = document.getElementById("previa");
  var resumo = document.getElementById("previa-resumo");
  var grade = document.getElementById("previa-grade");
  var campoRodadas = document.getElementById("rodadas");
  var ajudaRodadas = document.getElementById("rodadas-ajuda");
  var campoAssinatura = document.getElementById("assinatura-tema");

  // Cada troca de tema ganha um número novo. Imagens de um tema anterior que
  // terminarem de carregar depois da troca são ignoradas.
  var geracao = 0;

  function temaEscolhido() {
    for (var i = 0; i < temas.length; i++) {
      if (temas[i].nome === seletor.value) return temas[i];
    }
    return null;
  }

  function mostrarPrevia(ajustarRodadas) {
    var tema = temaEscolhido();
    geracao++;
    var minhaGeracao = geracao;
    grade.textContent = "";
    // O servidor confere que o tema criado é o mesmo desta prévia.
    campoAssinatura.value = tema ? tema.assinatura : "";

    if (!tema) {
      previa.hidden = true;
      campoRodadas.removeAttribute("max");
      return;
    }

    var total = tema.itens.length;
    var carregadas = 0;
    var quebradas = 0;

    function atualizarResumo() {
      if (minhaGeracao !== geracao) return;
      var texto = total + " itens. Imagens carregadas: " + carregadas + " de " + total + ".";
      if (quebradas > 0) {
        texto += " " + quebradas + " não carregaram (em vermelho).";
      }
      resumo.textContent = texto;
      resumo.className = quebradas > 0 ? "texto-erro" : "";
    }

    tema.itens.forEach(function (item) {
      var cartao = document.createElement("figure");
      cartao.className = "miniatura";
      var img = document.createElement("img");
      img.alt = item.nome;
      img.referrerPolicy = "no-referrer";
      img.addEventListener("load", function () {
        carregadas++;
        atualizarResumo();
      });
      img.addEventListener("error", function () {
        quebradas++;
        cartao.classList.add("quebrada");
        atualizarResumo();
      });
      img.src = item.imagem;
      var legenda = document.createElement("figcaption");
      legenda.textContent = item.nome;
      legenda.title = item.nome;
      cartao.appendChild(img);
      cartao.appendChild(legenda);
      grade.appendChild(cartao);
    });

    previa.hidden = false;
    atualizarResumo();

    campoRodadas.max = total;
    if (ajustarRodadas) {
      campoRodadas.value = Math.min(RODADAS_PADRAO, total);
    } else if (Number(campoRodadas.value) > total) {
      campoRodadas.value = total;
    }
    ajudaRodadas.textContent = "Entre 1 e " + total + ". Se for menos que " + total +
      ", os itens são sorteados.";
  }

  seletor.addEventListener("change", function () { mostrarPrevia(true); });

  // ----- Modo: no "cada um no seu ritmo", as "rodadas" são o número de itens -----

  var tituloRodadas = document.getElementById("rodadas-titulo");
  var dicaDoModo = document.getElementById("rodadas-modo");

  function atualizarModo() {
    var marcado = document.querySelector('input[name="modo"]:checked');
    var individual = marcado && marcado.value === "individual";
    tituloRodadas.textContent = individual ? "3. Número de itens" : "3. Rodadas";
    dicaDoModo.hidden = !individual;
  }

  Array.prototype.forEach.call(document.querySelectorAll('input[name="modo"]'), function (opcao) {
    opcao.addEventListener("change", atualizarModo);
  });
  atualizarModo();
  // Ao voltar com erro, mantém o número de rodadas que o admin digitou.
  mostrarPrevia(false);

  // ----- Faixas: adicionar e remover -----

  var listaFaixas = document.getElementById("faixas");
  var modelo = document.getElementById("modelo-faixa");
  var botaoAdicionar = document.getElementById("adicionar-faixa");
  var minFaixas = Number(listaFaixas.dataset.min);
  var maxFaixas = Number(listaFaixas.dataset.max);

  function quantidadeFaixas() {
    return listaFaixas.querySelectorAll(".faixa").length;
  }

  function atualizarBotoesFaixa() {
    var n = quantidadeFaixas();
    listaFaixas.querySelectorAll(".remover-faixa").forEach(function (botao) {
      botao.disabled = n <= minFaixas;
    });
    botaoAdicionar.disabled = n >= maxFaixas;
  }

  botaoAdicionar.addEventListener("click", function () {
    if (quantidadeFaixas() >= maxFaixas) return;
    var nova = modelo.content.firstElementChild.cloneNode(true);
    listaFaixas.appendChild(nova);
    atualizarBotoesFaixa();
    nova.querySelector(".rotulo").focus();
  });

  listaFaixas.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".remover-faixa");
    if (!botao || quantidadeFaixas() <= minFaixas) return;
    botao.closest(".faixa").remove();
    atualizarBotoesFaixa();
  });

  atualizarBotoesFaixa();
})();

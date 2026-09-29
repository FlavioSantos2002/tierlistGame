// Partes comuns das telas de partida do admin (ao vivo e individual):
// copiar os links, o botão "Remover" de cada jogador e as respostas do polling.
var Admin = (function () {
  "use strict";

  var el = TierList.el;
  var secao = document.getElementById("ao-vivo");
  var aviso = document.getElementById("aviso");

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

  // ----- Botão "Remover" -----

  // Formulário POST normal (com o token CSRF), igual aos outros botões do painel.
  // A página recarrega e mostra a mensagem do servidor (removido ou o motivo de
  // não ter removido, como "último jogador ativo").
  function botaoRemover(jogador) {
    var formulario = el("form", "form-remover");
    formulario.method = "post";
    formulario.action = secao.getAttribute("data-url-remover").replace(/\/0$/, "/" + jogador.id);
    var token = el("input");
    token.type = "hidden";
    token.name = "csrf_token";
    token.value = secao.getAttribute("data-csrf");
    formulario.appendChild(token);
    var botao = el("button", "perigo pequeno", "Remover");
    botao.type = "submit";
    formulario.appendChild(botao);
    formulario.addEventListener("submit", function (evento) {
      if (!window.confirm(textoDeRemover(jogador.nome))) evento.preventDefault();
    });
    return formulario;
  }

  // O efeito da remoção muda com o modo: no ao vivo, as rodadas já fechadas
  // não são recalculadas (decisão do dono); no individual, as respostas saem
  // de todos os resultados.
  function textoDeRemover(nome) {
    var inicio = "Remover " + nome + " da partida? Não dá para desfazer: o link dele para de funcionar";
    if (secao.getAttribute("data-modo") === "individual") {
      return inicio + " e as respostas dele deixam de entrar nos resultados.";
    }
    return inicio + " e o voto dele na votação em andamento é descartado. " +
      "As rodadas já fechadas ficam como estão.";
  }

  // ----- Respostas do polling -----

  function mostrarAviso(texto) {
    aviso.textContent = texto;
    aviso.hidden = false;
  }

  function criarSincronizador(desenhar, intervaloMs) {
    var sincronizador = TierList.criarSincronizador({
      urlEstado: secao.getAttribute("data-url-estado"),
      intervaloMs: intervaloMs,
      desenhar: desenhar,
      aoResponder: function (status) {
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
    });
    return sincronizador;
  }

  return {
    secao: secao,
    nomesEstados: JSON.parse(secao.getAttribute("data-nomes-estados")),
    botaoRemover: botaoRemover,
    criarSincronizador: criarSincronizador
  };
})();

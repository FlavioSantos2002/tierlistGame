// Cenários da tela do admin no modo individual: progresso, encerrar, remover, listas.
"use strict";

const LISTA_VAZIA = { tier_list: [[], []], pulados: [] };
const LISTA_ANA = {
  tier_list: [[{ id: 11, nome: "Pikachu", imagem: GIF, novo: false }], []], pulados: [],
};

function estadoIndividual(versao, estadoPartida, jogadores, geral = null) {
  return { versao, modo: "individual", estado: estadoPartida, tema: "T", total_itens: 12,
           faixas: FAIXAS, jogadores, geral };
}

const JOGADORES = [
  { id: 41, nome: "Ana", entrou: true, removido: false, finalizado: false, respondidos: 7, lista: LISTA_ANA },
  { id: 42, nome: "Pedro", entrou: true, removido: false, finalizado: true, respondidos: 12, lista: LISTA_ANA },
  { id: 43, nome: "Bia", entrou: true, removido: true, finalizado: false, respondidos: 3, lista: null },
  { id: 44, nome: "Caio", entrou: false, removido: false, finalizado: false, respondidos: 0, lista: LISTA_VAZIA },
];

const formEncerrar = () => document.getElementById("form-encerrar");

const CENARIOS = {
  async progresso_de_cada_jogador() {
    (await pendente("GET")).responder(200, estadoIndividual("1", "aberta", JOGADORES, LISTA_ANA));
    await depois();
    const linhas = Array.from(document.querySelectorAll("#vivo-jogadores li")).map((l) => l.textContent);
    checar(linhas[0].includes("Ana:") && linhas[0].includes("7 de 12"), "Ana: " + linhas[0]);
    checar(linhas[1].includes("finalizou"), "Pedro: " + linhas[1]);
    checar(linhas[2].includes("removido"), "Bia: " + linhas[2]);
    checar(linhas[3].includes("ainda não abriu o link"), "Caio: " + linhas[3]);
    // Remover só nos ativos (Ana, Pedro, Caio).
    checar(document.querySelectorAll("#vivo-jogadores .form-remover").length === 3, "botões Remover");
  },

  async listas_de_cada_jogador_e_geral() {
    (await pendente("GET")).responder(200, estadoIndividual("1", "aberta", JOGADORES, LISTA_ANA));
    await depois();
    const listas = Array.from(document.querySelectorAll("#vivo-listas details summary")).map((s) => s.textContent);
    checar(listas.length === 3, "listas: " + listas);            // a removida não aparece
    checar(texto("#vivo-listas").includes("Ainda sem respostas."), "lista vazia do Caio");
    checar(texto("#vivo-tier").includes("Pikachu"), "geral não desenhada");
  },

  async confirmacao_avisa_quando_ninguem_finalizou() {
    const ninguem = JOGADORES.map((j) => Object.assign({}, j, { finalizado: false }));
    (await pendente("GET")).responder(200, estadoIndividual("1", "aberta", ninguem));
    await depois();
    checar(formEncerrar().getAttribute("data-confirmacao").includes("Ninguém finalizou ainda"),
      "confirmação sem o aviso de resultado vazio");
    checar(texto("#vivo-tier").includes("Ninguém finalizou ainda."), "geral sem o aviso");
    (await pendente("GET")).responder(200, estadoIndividual("2", "aberta", JOGADORES, LISTA_ANA));
    await depois();
    checar(formEncerrar().getAttribute("data-confirmacao").includes("Quem não finalizou fica de fora"),
      "confirmação normal quando alguém finalizou");
  },

  async remover_pede_confirmacao_com_o_texto_do_modo() {
    (await pendente("GET")).responder(200, estadoIndividual("1", "aberta", JOGADORES, LISTA_ANA));
    await depois();
    responderConfirm(false);
    const evento = new Event("submit", { cancelable: true });
    document.querySelector("#vivo-jogadores .form-remover").dispatchEvent(evento);
    checar(evento.defaultPrevented, "enviou mesmo cancelando a confirmação");
    checar(confirmacoes[0].includes("Remover Ana") &&
      confirmacoes[0].includes("as respostas dele deixam de entrar nos resultados"),
      "texto da confirmação: " + confirmacoes[0]);
    checar(!confirmacoes[0].includes("rodadas"), "texto do ao vivo no individual: " + confirmacoes[0]);
  },

  async encerrada_sem_botoes() {
    (await pendente("GET")).responder(200, estadoIndividual("1", "encerrada", JOGADORES, LISTA_ANA));
    await depois();
    checar(formEncerrar().hidden, "Encerrar visível com a partida encerrada");
    checar(document.querySelectorAll("#vivo-jogadores .form-remover").length === 0,
      "Remover visível com a partida encerrada");
  },

  async lista_aberta_continua_aberta_no_redesenho() {
    (await pendente("GET")).responder(200, estadoIndividual("1", "aberta", JOGADORES, LISTA_ANA));
    await depois();
    document.querySelector('#vivo-listas details[data-jogador="42"]').open = true;
    (await pendente("GET")).responder(200, estadoIndividual("2", "aberta", JOGADORES, LISTA_ANA));
    await depois();
    checar(document.querySelector('#vivo-listas details[data-jogador="42"]').open, "a lista fechou sozinha");
  },

  async polling_a_cada_5_segundos() {
    (await pendente("GET")).responder(200, estadoIndividual("1", "aberta", JOGADORES));
    const segundo = await pendente("GET");
    const intervalo = segundo.quando - Falso.pedidos[0].quando;
    checar(intervalo >= 4900 && intervalo < 6000, "intervalo: " + intervalo + " ms");
  },
};

rodarCenarios(CENARIOS);

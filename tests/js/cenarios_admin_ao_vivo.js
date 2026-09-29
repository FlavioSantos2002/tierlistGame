// Cenários da tela do admin no modo ao vivo: o botão "Remover".
"use strict";

function estadoAoVivo(versao, estadoPartida, jogadores) {
  return {
    versao, estado: estadoPartida, tema: "T", rodada: 1, total_rodadas: 3, faixas: FAIXAS,
    item: { nome: "Pikachu", imagem: GIF },
    presenca: { online: 2, offline: 0, faltam: 1 },
    distribuicao: null, abstencoes: null, tier_list: [[], []], pulados: [],
    jogadores,
  };
}

const JOGADORES = [
  { id: 41, nome: "Ana", entrou: true, online: true, removido: false, acao: "votou" },
  { id: 42, nome: "Beto", entrou: true, online: true, removido: false, acao: null },
  { id: 43, nome: "Caio", entrou: true, online: false, removido: true, acao: null },
];

const formularios = () => Array.from(document.querySelectorAll("#vivo-jogadores .form-remover"));

function enviar(formulario) {
  // Evento de envio "de mentira": roda a confirmação sem sair da página.
  const evento = new Event("submit", { cancelable: true });
  formulario.dispatchEvent(evento);
  return !evento.defaultPrevented;
}

const CENARIOS = {
  async remover_aparece_so_nos_ativos_com_a_url_certa() {
    (await pendente("GET")).responder(200, estadoAoVivo("1", "votacao", JOGADORES));
    await depois();
    const lista = formularios();
    checar(lista.length === 2, "botões Remover: " + lista.length);
    checar(lista[0].getAttribute("action") === "/admin/partida/7/remover/41", "URL: " + lista[0].getAttribute("action"));
    checar(lista[1].getAttribute("action") === "/admin/partida/7/remover/42", "URL: " + lista[1].getAttribute("action"));
    checar(lista[0].querySelector('input[name="csrf_token"]').value === "token-de-teste", "sem token CSRF");
    checar(texto("#vivo-jogadores").includes("removido"), "o removido não aparece marcado");
  },

  async remover_pede_confirmacao() {
    (await pendente("GET")).responder(200, estadoAoVivo("1", "votacao", JOGADORES));
    await depois();
    responderConfirm(false);
    checar(!enviar(formularios()[1]), "enviou mesmo cancelando a confirmação");
    checar(confirmacoes[0].includes("Remover Beto") && confirmacoes[0].includes("Não dá para desfazer"),
      "texto da confirmação: " + confirmacoes[0]);
    // No ao vivo, as rodadas já fechadas não mudam: a confirmação não pode dizer o contrário.
    checar(confirmacoes[0].includes("As rodadas já fechadas ficam como estão."),
      "confirmação sem avisar das rodadas fechadas: " + confirmacoes[0]);
    checar(!confirmacoes[0].includes("respostas dele"), "texto do modo individual no ao vivo: " + confirmacoes[0]);
    responderConfirm(true);
    checar(enviar(formularios()[1]), "não enviou depois de confirmar");
  },

  async sem_remover_depois_que_a_partida_termina() {
    (await pendente("GET")).responder(200, estadoAoVivo("1", "encerrada", JOGADORES));
    await depois();
    checar(formularios().length === 0, "botão Remover com a partida encerrada");
  },
};

rodarCenarios(CENARIOS);

// Cenários da tela do jogador no modo individual. O cenário vem depois do # na URL.
"use strict";

const NOMES = ["Pikachu", "Charizard", "Mew"];

// respostas: uma por item, na ordem do jogador. undefined = sem resposta,
// null = pulou, número = faixa. `revisoes` (opcional): revisão de cada item.
function preenchendo(versao, respostas, revisoes = []) {
  const itens = NOMES.map((nome, i) => ({
    id: 11 + i,
    nome,
    imagem: GIF,
    respondido: respostas[i] !== undefined,
    faixa: respostas[i] === undefined ? null : respostas[i],
    revisao: revisoes[i] !== undefined ? revisoes[i] : (respostas[i] === undefined ? 0 : 1),
  }));
  return {
    versao, modo: "individual", estado: "aberta", tema: "Tema de teste",
    total_itens: itens.length, faixas: FAIXAS,
    eu: { nome: "Ana", finalizado: false, respondidos: itens.filter((i) => i.respondido).length },
    itens, resultado: null,
  };
}

function lista(itensPorFaixa, pulados = []) {
  const item = (nome) => ({ id: NOMES.indexOf(nome) + 11, nome, imagem: GIF, novo: false });
  return { tier_list: itensPorFaixa.map((nomes) => nomes.map(item)), pulados: pulados.map(item) };
}

function comResultado(versao, mudancas) {
  return Object.assign({
    versao, modo: "individual", estado: "aberta", tema: "Tema de teste",
    total_itens: 3, faixas: FAIXAS,
    eu: { nome: "Ana", finalizado: true, respondidos: 3 },
    itens: null,
    resultado: {
      geral: lista([["Pikachu", "Mew"], ["Charizard"]]),
      minha: lista([["Pikachu"], ["Charizard"]], ["Mew"]),
      compatibilidade: 75,
      outros: [Object.assign({ nome: "Beto" }, lista([["Pikachu", "Mew"], ["Charizard"]]))],
      faltam: ["Caio", "Duda"],
    },
  }, mudancas);
}

const jogo = () => document.getElementById("jogo");
const itemNoTopo = () => jogo().querySelector(".item-atual figcaption")?.textContent;
const botoesFaixa = () => Array.from(jogo().querySelectorAll(".botao-faixa"));
const botao = (rotulo) => Array.from(jogo().querySelectorAll("button"))
  .find((b) => b.textContent.trim() === rotulo);

const CENARIOS = {
  // Abre no primeiro item sem resposta, com o progresso certo.
  async comeca_no_primeiro_sem_resposta() {
    (await pendente("GET")).responder(200, preenchendo("1", [0, undefined, undefined]));
    await depois();
    checar(itemNoTopo() === "Charizard", "não abriu no primeiro sem resposta: " + itemNoTopo());
    checar(texto("#jogo").includes("1 de 3"), "progresso errado");
    checar(botao("Finalizar").disabled, "Finalizar ativo com itens sem resposta");
  },

  // Escolher uma faixa envia a resposta (com a revisão do item) e avança.
  async responder_envia_revisao_e_avanca() {
    (await pendente("GET")).responder(200, preenchendo("1", [undefined, undefined, undefined]));
    await depois();
    botoesFaixa()[1].click();                                     // A no Pikachu
    const post = await pendente("POST");
    checar(post.url === "/api/responder/X", "URL errada: " + post.url);
    checar(JSON.stringify(post.corpo) === JSON.stringify({ item: 11, faixa: 1, revisao: 0 }),
      "corpo errado: " + JSON.stringify(post.corpo));
    checar(Array.from(jogo().querySelectorAll("button")).every((b) => b.disabled),
      "botões ativos durante o envio");
    post.responder(200, preenchendo("2", [1, undefined, undefined]));
    await depois();
    checar(itemNoTopo() === "Charizard", "não avançou para o próximo item");
    checar(texto("#jogo").includes("1 de 3"), "progresso não atualizou");
  },

  // "Pular" também é resposta (faixa null) e também avança.
  async pular_envia_null() {
    (await pendente("GET")).responder(200, preenchendo("1", [undefined, undefined, undefined]));
    await depois();
    botao("Pular").click();
    const post = await pendente("POST");
    checar(post.corpo.faixa === null && post.corpo.item === 11, "pular mandou " + JSON.stringify(post.corpo));
    post.responder(200, preenchendo("2", [null, undefined, undefined]));
    await depois();
    checar(itemNoTopo() === "Charizard", "não avançou depois de pular");
  },

  // Resposta recusada (409): fica no mesmo item e mostra o aviso.
  async resposta_recusada_nao_avanca() {
    (await pendente("GET")).responder(200, preenchendo("1", [undefined, undefined, undefined]));
    await depois();
    botoesFaixa()[0].click();
    (await pendente("POST")).responder(409, {
      erro: "Essa resposta já tinha mudado por outro envio. A tela foi atualizada.",
      estado: preenchendo("2", [1, undefined, undefined], [2]),
    });
    await depois();
    checar(itemNoTopo() === "Pikachu", "avançou mesmo com a resposta recusada");
    checar(texto("#jogo").includes("Sua resposta: A"), "não mostrou a resposta que vale");
    checar(texto("#aviso").includes("já tinha mudado"), "sem aviso do 409");
  },

  // "Voltar" mostra o item anterior com a resposta dele destacada.
  async voltar_mostra_a_resposta_anterior() {
    (await pendente("GET")).responder(200, preenchendo("1", [1, undefined, undefined]));
    await depois();
    checar(botao("Voltar") && !botao("Voltar").disabled, "Voltar desativado no 2º item");
    botao("Voltar").click();
    await depois();
    checar(itemNoTopo() === "Pikachu", "Voltar não foi para o anterior");
    checar(botoesFaixa()[1].classList.contains("escolhida"), "a resposta anterior não está destacada");
    checar(botao("Voltar").disabled, "Voltar ativo no primeiro item");
  },

  // Tocar num item da lista pessoal leva a ele para trocar a resposta.
  async tocar_na_lista_para_trocar() {
    (await pendente("GET")).responder(200, preenchendo("1", [0, 1, undefined], [3, 1]));
    await depois();
    const miniatura = Array.from(jogo().querySelectorAll(".miniatura-tier.tocavel"))
      .find((m) => m.textContent === "Pikachu");
    checar(miniatura, "o Pikachu não está tocável na lista pessoal");
    miniatura.click();
    await depois();
    checar(itemNoTopo() === "Pikachu", "tocar na lista não abriu o item");
    botao("Pular").click();
    const post = await pendente("POST");
    checar(post.corpo.item === 11 && post.corpo.faixa === null && post.corpo.revisao === 3,
      "troca mandou " + JSON.stringify(post.corpo));
  },

  // Depois do último item: tela de revisão, e "Finalizar" libera com tudo respondido.
  async ultimo_item_vai_para_a_revisao_e_finaliza_com_confirmacao() {
    (await pendente("GET")).responder(200, preenchendo("1", [0, 1, undefined]));
    await depois();
    botoesFaixa()[0].click();                                     // responde o Mew
    (await pendente("POST")).responder(200, preenchendo("2", [0, 1, 0]));
    await depois();
    checar(texto("#jogo").includes("Todos os itens têm resposta"), "não foi para a revisão");
    checar(!botao("Finalizar").disabled, "Finalizar desativado com tudo respondido");

    responderConfirm(false);                                      // desiste na confirmação
    botao("Finalizar").click();
    await depois();
    checar(confirmacoes.length === 1 && confirmacoes[0].includes("não dá para mudar"),
      "não pediu confirmação: " + confirmacoes);
    checar(quantos("POST") === 1, "finalizou mesmo cancelando");

    responderConfirm(true);
    botao("Finalizar").click();
    const post = await pendente("POST");
    checar(post.url === "/api/finalizar/X", "não chamou finalizar");
  },

  // Durante o envio, tocar na lista (clique ou teclado) não muda de tela: a
  // resposta, quando chega, não desfaz nada. Depois do envio, tocar volta a funcionar.
  async lista_nao_navega_durante_o_envio() {
    (await pendente("GET")).responder(200, preenchendo("1", [0, 1, undefined]));
    await depois();
    botoesFaixa()[0].click();                                     // responde o Mew (último)
    const post = await pendente("POST");
    const pikachu = () => Array.from(jogo().querySelectorAll(".miniatura-tier.tocavel"))
      .find((m) => m.textContent === "Pikachu");
    checar(pikachu().getAttribute("aria-disabled") === "true", "miniatura sem aria-disabled no envio");
    pikachu().click();
    pikachu().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await depois();
    checar(itemNoTopo() === "Mew", "a tela mudou durante o envio: " + itemNoTopo());
    post.responder(200, preenchendo("2", [0, 1, 0]));
    await depois();
    checar(texto("#jogo").includes("Todos os itens têm resposta"), "não foi para a revisão");
    checar(pikachu().getAttribute("aria-disabled") === null, "miniatura continuou desativada");
    pikachu().click();
    await depois();
    checar(itemNoTopo() === "Pikachu", "tocar na lista não funciona depois do envio");
  },

  // O polling (versão nova) não tira a pessoa do item que ela está vendo.
  async polling_nao_perde_a_posicao() {
    (await pendente("GET")).responder(200, preenchendo("1", [0, undefined, undefined]));
    await depois();
    botao("Voltar").click();
    await depois();
    checar(itemNoTopo() === "Pikachu", "Voltar não funcionou");
    (await pendente("GET")).responder(200, preenchendo("2", [0, undefined, undefined]));
    await depois();
    checar(itemNoTopo() === "Pikachu", "o polling mudou o item da tela");
  },

  // Neste modo o polling é a cada 5 segundos.
  async polling_a_cada_5_segundos() {
    (await pendente("GET")).responder(200, preenchendo("1", [undefined, undefined, undefined]));
    const segundo = await pendente("GET");
    const primeiro = Falso.pedidos[0];
    const intervalo = segundo.quando - primeiro.quando;
    checar(intervalo >= 4900 && intervalo < 6000, "intervalo entre consultas: " + intervalo + " ms");
  },

  // Depois de finalizar: compatibilidade, quem falta, a geral e as listas com nome.
  async resultado_mostra_tudo() {
    (await pendente("GET")).responder(200, comResultado("1"));
    await depois();
    const tela = texto("#jogo");
    checar(tela.includes("Você finalizou!"), "título");
    checar(tela.includes("75%"), "compatibilidade");
    checar(tela.includes("Faltam: Caio, Duda"), "quem falta");
    checar(tela.includes("Tier list geral"), "lista geral");
    checar(tela.includes("A sua tier list"), "lista própria");
    checar(tela.includes("Tier list de Beto"), "lista dos outros com nome");
    checar(!botao("Finalizar"), "botão Finalizar depois de finalizar");
  },

  async compatibilidade_sem_item_em_comum_mostra_traco() {
    const estado = comResultado("1");
    estado.resultado.compatibilidade = null;
    (await pendente("GET")).responder(200, estado);
    await depois();
    checar(jogo().querySelector(".compatibilidade-numero").textContent === "—", "não mostrou o traço");
  },

  // Encerrada sem ter finalizado: vê os resultados, sem lista nem compatibilidade.
  async encerrada_sem_ter_finalizado() {
    const estado = comResultado("1", {
      estado: "encerrada",
      eu: { nome: "Ana", finalizado: false, respondidos: 1 },
    });
    estado.resultado.minha = null;
    estado.resultado.compatibilidade = null;
    estado.resultado.faltam = [];
    (await pendente("GET")).responder(200, estado);
    await depois();
    const tela = texto("#jogo");
    checar(tela.includes("Resultado final"), "título");
    checar(tela.includes("suas respostas ficaram de fora"), "aviso de quem não finalizou");
    checar(!tela.includes("A sua tier list") && !jogo().querySelector(".compatibilidade-numero"),
      "mostrou lista ou compatibilidade de quem não finalizou");
    checar(tela.includes("Tier list de Beto"), "não mostrou as listas de quem finalizou");
  },

  async removido_para_de_vez() {
    (await pendente("GET")).responder(200, preenchendo("1", [undefined, undefined, undefined]));
    await depois();
    (await pendente("GET")).responder(403, { removido: true, mensagem: "Você foi removido desta partida" });
    await esperar(12000);
    checar(texto("#jogo").includes("Você foi removido desta partida"), "não mostrou a mensagem");
    checar(quantos("GET") === 2, "continuou consultando depois de removido");
  },
};

rodarCenarios(CENARIOS);

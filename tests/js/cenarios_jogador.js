// Cenários da tela do jogador: cruzamento de polling e ações, partida apagada,
// tempo esgotado e respostas atrasadas. O cenário vem depois do # na URL e o
// resultado ("OK" ou "FALHOU: ...") é escrito em <pre id="resultado">.
// (Código só de teste: pode usar JavaScript moderno.)
"use strict";

const GIF = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
const APAGADA = { apagada: true, mensagem: "Esta partida foi encerrada pelo admin" };

function estado(versao, mudancas = {}) {
  const base = {
    versao,
    estado: "votacao",
    tema: "Tema de teste",
    rodada: 1,
    total_rodadas: 3,
    faixas: [
      { indice: 0, rotulo: "S", descricao: "", cor: "#ff7f7f" },
      { indice: 1, rotulo: "A", descricao: "", cor: "#1f3a93" },
    ],
    item: { nome: "Pikachu", imagem: GIF },
    presenca: { online: 2, offline: 0, faltam: 2 },
    distribuicao: null,
    abstencoes: null,
    tier_list: [[], []],
    pulados: [],
    eu: { nome: "Ana", voto: null, pulou: false, continuou: false, revisao: 0 },
  };
  const eu = Object.assign({}, base.eu, mudancas.eu || {});
  return Object.assign(base, mudancas, { eu });
}

// ----- Auxiliares -----

const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));
const depois = () => esperar(50);   // deixa as promessas e o redesenho terminarem

async function pendente(metodo) {
  for (let i = 0; i < 400; i++) {
    const pedido = Falso.pedidos.find((p) => p.metodo === metodo && !p.terminado);
    if (pedido) return pedido;
    await esperar(25);
  }
  throw new Error(`nenhum ${metodo} pendente apareceu`);
}

const jogo = () => document.getElementById("jogo");
const aviso = () => document.getElementById("aviso");
const textoDaTela = () => jogo().textContent;
const botoesFaixa = () => Array.from(jogo().querySelectorAll(".botao-faixa"));
const todosDesativados = () =>
  Array.from(jogo().querySelectorAll("button")).every((botao) => botao.disabled);
const quantos = (metodo) => Falso.pedidos.filter((p) => p.metodo === metodo).length;

function checar(condicao, mensagem) {
  if (!condicao) throw new Error(mensagem);
}

// ----- Cenários -----

const CENARIOS = {
  // Voto com um polling no ar, e outro jogador mudando o estado no meio.
  async ordem_do_voto_com_polling() {
    (await pendente("GET")).responder(200, estado("1.a"));
    await depois();
    const get = await pendente("GET");                 // próximo polling no ar
    botoesFaixa()[0].click();                          // vota em S
    await depois();
    checar(quantos("POST") === 0, "o POST saiu com um GET no ar");
    checar(todosDesativados(), "botões ativos logo depois do clique");

    // Outro jogador votou: o GET traz uma versão nova e a tela é redesenhada.
    get.responder(200, estado("2.a", { presenca: { online: 2, offline: 0, faltam: 1 } }));
    await depois();
    checar(todosDesativados(), "o redesenho no meio da ação liberou os botões");

    const post = await pendente("POST");
    checar(post.corpo.faixa === 0 && post.corpo.rodada === 1 && post.corpo.revisao === 0,
      "corpo do POST errado: " + JSON.stringify(post.corpo));
    post.responder(200, estado("3.a", { eu: { voto: 0 } }));
    await depois();
    checar(textoDaTela().includes("Seu voto: S"), "o voto não aparece na tela");
    checar(!todosDesativados(), "os botões não voltaram depois da ação");
    checar(Falso.maximoNoAr() === 1, "houve mais de um pedido no ar ao mesmo tempo");
  },

  // A resposta do próprio POST diz que a partida foi apagada.
  async apagada_durante_o_post() {
    (await pendente("GET")).responder(200, estado("1.a"));
    await depois();
    botoesFaixa()[1].click();
    (await pendente("POST")).responder(404, APAGADA);
    await esperar(5000);                               // sobra tempo para redesenho e polling
    checar(textoDaTela().includes("encerrada pelo admin"), "a tela da partida voltou");
    checar(Falso.pedidos.length === 2, `houve pedidos depois de apagar (${Falso.pedidos.length})`);
  },

  // A ação estava na fila atrás de um polling, e o polling diz que a partida foi apagada.
  async apagada_com_acao_na_fila() {
    (await pendente("GET")).responder(200, estado("1.a"));
    await depois();
    const get = await pendente("GET");
    botoesFaixa()[1].click();                          // fica na fila atrás do GET
    get.responder(404, APAGADA);
    await esperar(5000);
    checar(textoDaTela().includes("encerrada pelo admin"), "a tela da partida voltou");
    checar(quantos("POST") === 0, "a ação foi enviada depois de a partida ser apagada");
    checar(Falso.pedidos.length === 2, `houve pedidos depois de apagar (${Falso.pedidos.length})`);
  },

  // Um polling que nunca responde: aviso de conexão e polling retomado.
  async tempo_esgotado_no_polling() {
    (await pendente("GET")).responder(200, estado("1.a"));
    await depois();
    await pendente("GET");                             // este nunca responde
    await esperar(8500);
    checar(!aviso().hidden && aviso().textContent.includes("Sem conexão"), "sem aviso de conexão");
    (await pendente("GET")).responder(200, estado("1.a"));   // o polling voltou sozinho
    await depois();
    checar(aviso().hidden, "o aviso de conexão não sumiu quando a conexão voltou");
  },

  // Uma ação que nunca responde: botões voltam e o POST não é reenviado.
  async tempo_esgotado_na_acao() {
    (await pendente("GET")).responder(200, estado("1.a"));
    await depois();
    botoesFaixa()[0].click();
    await pendente("POST");                            // nunca responde
    await esperar(8500);
    checar(!todosDesativados(), "os botões continuaram travados");
    checar(aviso().textContent.includes("Sem conexão"), "sem aviso de conexão");
    await esperar(6000);
    checar(quantos("POST") === 1, `o POST foi reenviado sozinho (${quantos("POST")})`);
    checar(quantos("GET") >= 2, "o polling não voltou depois da ação");
  },

  // Navegador sem cancelamento: a resposta de um GET que estourou o tempo
  // chega depois de uma mais nova e precisa ser descartada.
  async resposta_atrasada_descartada() {
    Falso.ignorarCancelamento = true;
    (await pendente("GET")).responder(200, estado("1.a"));
    await depois();
    const atrasado = await pendente("GET");
    await esperar(8500);                               // esgota o tempo desse GET
    const novo = await pendente("GET");
    checar(novo !== atrasado, "o polling não seguiu depois do tempo esgotado");
    novo.responder(200, estado("3.a", { eu: { voto: 1 } }));
    await depois();
    checar(textoDaTela().includes("Seu voto: A"), "o estado novo não apareceu");
    atrasado.responder(200, estado("2.a"));            // chega tarde, com o estado velho
    await depois();
    checar(textoDaTela().includes("Seu voto: A"), "a resposta atrasada sobrescreveu a tela");
  },

  // Cenário do parecer, visto do navegador: o 1º voto esgota o tempo, o 2º sai
  // com a MESMA revisão (a tela não mudou) e quem protege é o servidor. Quando
  // ele recusa por revisão (409), a tela mostra a escolha que valeu e o
  // próximo envio já usa a revisão nova.
  async revisao_enviada_e_recusa_409() {
    (await pendente("GET")).responder(200, estado("1.a"));
    await depois();
    botoesFaixa()[0].click();                          // vota S
    const primeiro = await pendente("POST");           // nunca responde
    await esperar(8500);
    botoesFaixa()[1].click();                          // vota A
    const segundo = await pendente("POST");
    checar(segundo !== primeiro, "o segundo voto não saiu");
    checar(primeiro.corpo.revisao === 0 && segundo.corpo.revisao === 0,
      "revisões enviadas: " + primeiro.corpo.revisao + " e " + segundo.corpo.revisao);

    // O servidor já tinha aceitado outro envio: recusa e devolve o estado atual.
    segundo.responder(409, {
      erro: "Seu voto já tinha mudado por outro envio. A tela foi atualizada.",
      estado: estado("2.a", { eu: { voto: 0, revisao: 1 } }),
    });
    await depois();
    checar(textoDaTela().includes("Seu voto: S"), "a tela não mostrou a escolha que valeu");
    checar(!aviso().hidden && aviso().textContent.includes("já tinha mudado"), "sem aviso do 409");
    checar(!todosDesativados(), "os botões não voltaram depois do 409");

    botoesFaixa()[1].click();                          // tenta A de novo, agora sabendo da revisão 1
    const terceiro = await pendente("POST");
    checar(terceiro.corpo.revisao === 1, "o novo envio não usou a revisão atual");
  },

  // Item fechado sem nenhum voto (todos pularam ou o admin forçou).
  async item_sem_votos() {
    const resultado = estado("1.a", {
      estado: "resultado",
      distribuicao: [0, 0],
      abstencoes: 0,
      pulados: [{ nome: "Pikachu", imagem: GIF, novo: true }],
    });
    (await pendente("GET")).responder(200, resultado);
    await depois();
    checar(textoDaTela().includes("Ficou fora da tier list: nenhum voto recebido."), "texto do item sem votos");
    checar(textoDaTela().includes("Itens pulados"), "título da área de itens pulados");
  },
};

// ----- Execução -----

const saida = document.getElementById("resultado");
const nome = location.hash.slice(1);
if (nome === "listar") {
  saida.textContent = Object.keys(CENARIOS).join(",");
} else if (!CENARIOS[nome]) {
  saida.textContent = "FALHOU: cenário desconhecido: " + nome;
} else {
  CENARIOS[nome]().then(
    () => { saida.textContent = "OK"; },
    (erro) => { saida.textContent = "FALHOU: " + erro.message; }
  );
}

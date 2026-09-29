// Auxiliares dos cenários de JavaScript (código só de teste: pode ser moderno).
"use strict";

const GIF = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

const FAIXAS = [
  { indice: 0, rotulo: "S", descricao: "", cor: "#ff7f7f" },
  { indice: 1, rotulo: "A", descricao: "", cor: "#1f3a93" },
];

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

const quantos = (metodo) => Falso.pedidos.filter((p) => p.metodo === metodo).length;
const texto = (seletor = "body") => document.querySelector(seletor).textContent;

function checar(condicao, mensagem) {
  if (!condicao) throw new Error(mensagem);
}

// Troca o window.confirm por uma resposta fixa e conta as perguntas feitas.
const confirmacoes = [];
function responderConfirm(resposta) {
  window.confirm = (pergunta) => { confirmacoes.push(pergunta); return resposta; };
}

// Roda o cenário escolhido pelo # da URL e escreve o resultado em <pre id="resultado">.
function rodarCenarios(cenarios) {
  const saida = document.getElementById("resultado");
  const nome = location.hash.slice(1);
  if (nome === "listar") {
    saida.textContent = Object.keys(cenarios).join(",");
  } else if (!cenarios[nome]) {
    saida.textContent = "FALHOU: cenário desconhecido: " + nome;
  } else {
    cenarios[nome]().then(
      () => { saida.textContent = "OK"; },
      (erro) => { saida.textContent = "FALHOU: " + erro.message; }
    );
  }
}

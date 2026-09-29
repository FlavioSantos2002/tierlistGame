"""Rotas do jogador: entrada pelo link único e API do jogo.

API (todas pelo código secreto do jogador):
- GET  /api/estado/<codigo>     polling a cada 2 s: registra presença e devolve o estado
- POST /api/votar/<codigo>      {"rodada": N, "faixa": i, "revisao": R}
- POST /api/pular/<codigo>      {"rodada": N, "revisao": R}
- POST /api/continuar/<codigo>  {"rodada": N}
Modo individual:
- POST /api/responder/<codigo>  {"item": id, "faixa": i ou null ("pulei"), "revisao": R}
- POST /api/finalizar/<codigo>  {}

Os POST só aceitam Content-Type application/json. Um formulário de outro site
não consegue mandar esse tipo sem permissão do navegador (CORS), e é isso que
dispensa o token CSRF aqui.

"revisao" é a revisão do voto/resposta que estava na tela: impede que um
pedido antigo, que chegou atrasado ao servidor, desfaça uma escolha mais nova.
"""
import time

from flask import Blueprint, jsonify, render_template, request

import banco
import individual
import jogo

jogador = Blueprint("jogador", __name__)


@jogador.route("/j/<codigo>")
def tela(codigo):
    # O nome do jogador vem do banco, pelo código; nunca da URL.
    dados = banco.obter().execute(
        "SELECT j.nome, j.removido_em, p.tema_nome, p.modo"
        " FROM jogadores j JOIN partidas p ON p.id = j.partida_id"
        " WHERE j.codigo = ?",
        (codigo,),
    ).fetchone()
    if dados is None:
        # Código desconhecido: o caso comum é a partida ter sido apagada pelo admin.
        return render_template("jogador_sem_partida.html"), 404
    if dados["removido_em"] is not None:
        return render_template("jogador_removido.html"), 403
    return render_template("jogador.html", jogador=dados, codigo=codigo)


def resposta_json(dados, status=200):
    resposta = jsonify(dados)
    resposta.status_code = status
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def partida_apagada():
    return resposta_json(
        {"apagada": True, "mensagem": "Esta partida foi encerrada pelo admin"}, 404
    )


def jogador_removido():
    # Removido pelo admin: nenhuma ação é aceita (nem o polling registra presença).
    return resposta_json(
        {"removido": True, "mensagem": "Você foi removido desta partida"}, 403
    )


def buscar_jogador(con, codigo):
    return con.execute(
        "SELECT id, partida_id, nome, visto_em, removido_em FROM jogadores WHERE codigo = ?",
        (codigo,),
    ).fetchone()


def ler_inteiro(corpo, chave):
    """Lê um número inteiro do JSON (True/False não contam como número)."""
    valor = corpo.get(chave)
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise jogo.AcaoInvalida(f'O campo "{chave}" precisa ser um número inteiro.', status=400)
    return valor


@jogador.route("/api/estado/<codigo>")
def estado(codigo):
    con = banco.obter()
    with banco.transacao(con):
        agora = time.time()  # lido DEPOIS de pegar a trava (ver executar_acao)
        eu = buscar_jogador(con, codigo)
        if eu is None:
            return partida_apagada()
        if eu["removido_em"] is not None:
            return jogador_removido()
        jogo.registrar_presenca(con, eu, agora)
        jogo.verificar_avanco(con, eu["partida_id"], agora)
        dados = jogo.montar_estado(con, eu["partida_id"], agora, jogador_id=eu["id"])
    return resposta_json(dados)


def executar_acao(codigo, acao):
    """Parte comum de votar/pular/continuar.

    Tudo numa transação só: registra presença, faz a ação, verifica se a
    rodada fecha/avança e monta o estado. Se a ação for recusada, a presença
    continua registrada e o jogador recebe o estado atual junto com o erro.
    """
    if not request.is_json:
        return resposta_json({"erro": "Envie os dados como JSON."}, 415)
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return resposta_json({"erro": "JSON inválido."}, 400)

    con = banco.obter()
    with banco.transacao(con):
        # O horário é lido só DEPOIS de pegar a trava: a espera pela trava pode
        # levar segundos, e as regras de presença precisam do horário de agora,
        # não do horário em que a requisição chegou.
        agora = time.time()
        eu = buscar_jogador(con, codigo)
        if eu is None:
            return partida_apagada()
        if eu["removido_em"] is not None:
            return jogador_removido()
        jogo.registrar_presenca(con, eu, agora)
        erro, status = None, 200
        try:
            acao(con, eu, corpo, agora)
        except jogo.AcaoInvalida as problema:
            erro, status = str(problema), problema.status
        jogo.verificar_avanco(con, eu["partida_id"], agora)
        dados = jogo.montar_estado(con, eu["partida_id"], agora, jogador_id=eu["id"])

    if erro:
        return resposta_json({"erro": erro, "estado": dados}, status)
    return resposta_json(dados)


def ler_faixa_ou_nulo(corpo):
    """Faixa da resposta do modo individual: um inteiro, ou null para "pulei".

    O campo precisa vir no JSON (sem ele, não dá para saber o que a pessoa quis).
    """
    if "faixa" not in corpo:
        raise jogo.AcaoInvalida('Falta o campo "faixa" (use null para pular).', status=400)
    if corpo["faixa"] is None:
        return None
    return ler_inteiro(corpo, "faixa")


@jogador.route("/api/votar/<codigo>", methods=["POST"])
def votar(codigo):
    def acao(con, eu, corpo, agora):
        rodada = ler_inteiro(corpo, "rodada")
        faixa = ler_inteiro(corpo, "faixa")
        revisao = ler_inteiro(corpo, "revisao")
        jogo.votar(con, eu, rodada, faixa, revisao, agora)
    return executar_acao(codigo, acao)


@jogador.route("/api/pular/<codigo>", methods=["POST"])
def pular(codigo):
    def acao(con, eu, corpo, agora):
        rodada = ler_inteiro(corpo, "rodada")
        revisao = ler_inteiro(corpo, "revisao")
        jogo.pular(con, eu, rodada, revisao, agora)
    return executar_acao(codigo, acao)


@jogador.route("/api/continuar/<codigo>", methods=["POST"])
def continuar(codigo):
    def acao(con, eu, corpo, agora):
        jogo.continuar(con, eu, ler_inteiro(corpo, "rodada"))
    return executar_acao(codigo, acao)


# ----- Modo individual -----

@jogador.route("/api/responder/<codigo>", methods=["POST"])
def responder(codigo):
    def acao(con, eu, corpo, agora):
        item_id = ler_inteiro(corpo, "item")
        faixa = ler_faixa_ou_nulo(corpo)
        revisao = ler_inteiro(corpo, "revisao")
        individual.responder(con, eu, item_id, faixa, revisao, agora)
    return executar_acao(codigo, acao)


@jogador.route("/api/finalizar/<codigo>", methods=["POST"])
def finalizar(codigo):
    def acao(con, eu, corpo, agora):
        individual.finalizar(con, eu, agora)
    return executar_acao(codigo, acao)

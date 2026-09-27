"""Várias requisições ao mesmo tempo (como no gunicorn com threads).

A rodada precisa fechar e avançar exatamente uma vez, e nenhuma requisição
pode falhar com "database is locked".
"""
import contextlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import banco
from test_fluxo import login_admin

JOGADORES = [f"J{n}" for n in range(8)]


def ao_mesmo_tempo(tarefas):
    """Roda as funções em threads, soltando todas juntas.

    Devolve uma lista com o resultado de cada tarefa, na mesma ordem.
    Se alguma thread lançar exceção, `result()` relança a exceção aqui e o
    teste falha (uma thread com erro nunca "some" da contagem).
    """
    largada = threading.Barrier(len(tarefas))

    def rodar(tarefa):
        largada.wait(timeout=10)
        return tarefa()

    with ThreadPoolExecutor(max_workers=len(tarefas)) as executor:
        futuros = [executor.submit(rodar, tarefa) for tarefa in tarefas]
        return [futuro.result() for futuro in futuros]


def test_ao_mesmo_tempo_propaga_excecao():
    # Garante que o próprio auxiliar não esconde erros das threads.
    def falha():
        raise RuntimeError("erro na thread")

    with pytest.raises(RuntimeError, match="erro na thread"):
        ao_mesmo_tempo([lambda: 200, falha])


def test_votos_e_continuar_simultaneos(partida):
    p = partida(jogadores=JOGADORES, rodadas=3)
    p.entrar(*JOGADORES)

    for rodada in (1, 2, 3):
        # Cada jogador com seu próprio "celular" (cliente), votando junto
        # com consultas de estado de outros jogadores no meio.
        def votar(nome, faixa):
            cliente = p.app.test_client()
            return lambda: cliente.post(
                f"/api/votar/{p.codigos[nome]}", json={"rodada": rodada, "faixa": faixa, "revisao": 0}
            ).status_code

        def consultar(nome):
            cliente = p.app.test_client()
            return lambda: cliente.get(f"/api/estado/{p.codigos[nome]}").status_code

        tarefas = [votar(nome, rodada) for nome in JOGADORES] + [consultar(n) for n in JOGADORES]
        assert ao_mesmo_tempo(tarefas) == [200] * len(tarefas)
        assert p.fase() == ("resultado", rodada)
        assert p.item(rodada)["faixa_indice"] == rodada

        def continuar(nome):
            cliente = p.app.test_client()
            return lambda: cliente.post(
                f"/api/continuar/{p.codigos[nome]}", json={"rodada": rodada}
            ).status_code

        tarefas = [continuar(nome) for nome in JOGADORES] + [consultar(n) for n in JOGADORES]
        assert ao_mesmo_tempo(tarefas) == [200] * len(tarefas)
        esperado = ("votacao", rodada + 1) if rodada < 3 else ("encerrada", 3)
        assert p.fase() == esperado            # avançou uma rodada, nem mais nem menos

    situacoes = p.sql("SELECT situacao FROM itens WHERE partida_id = ?", (p.id,))
    assert [s["situacao"] for s in situacoes] == ["classificado"] * 3


def test_forcar_avanco_simultaneo_avanca_uma_vez(partida):
    p = partida(rodadas=3)

    def admin_forcando():
        cliente = p.app.test_client()
        token = login_admin(p, cliente)
        return lambda: cliente.post(
            f"/admin/partida/{p.id}/forcar",
            data={"csrf_token": token, "estado": "votacao", "rodada": "1"},
        ).status_code

    assert ao_mesmo_tempo([admin_forcando() for _ in range(6)]) == [302] * 6
    assert p.fase() == ("resultado", 1)        # 6 cliques, uma única mudança


def test_admin_e_jogadores_ao_mesmo_tempo(partida):
    # Forçar avanço junto com os jogadores continuando: ainda assim só uma rodada.
    p = partida(jogadores=JOGADORES, rodadas=3)
    p.entrar(*JOGADORES)
    for nome in JOGADORES:
        p.votar(nome, 0)
    assert p.fase() == ("resultado", 1)
    token = login_admin(p)

    def continuar(nome):
        cliente = p.app.test_client()
        return lambda: cliente.post(
            f"/api/continuar/{p.codigos[nome]}", json={"rodada": 1}
        ).status_code

    def forcar():
        return p.cliente.post(
            f"/admin/partida/{p.id}/forcar",
            data={"csrf_token": token, "estado": "resultado", "rodada": "1"},
        ).status_code

    status = ao_mesmo_tempo([continuar(n) for n in JOGADORES] + [forcar])
    # Quem continuar depois do avanço recebe 409 ("já está em outra fase"); tudo bem.
    assert len(status) == len(JOGADORES) + 1
    assert all(s in (200, 409) for s in status[:-1])
    assert status[-1] == 302
    assert p.fase() == ("votacao", 2)


def test_horario_lido_depois_de_pegar_a_trava(partida, monkeypatch):
    """A espera pela trava do banco não pode fazer as regras usarem um horário velho.

    Ana votou e foi vista em t=1000. Em t=1014 ela ainda está online (e, como
    votou, a rodada fecharia). O polling do admin chega em t=1014, mas só pega
    a trava em t=1016, quando já não há ninguém online: a rodada tem de
    continuar aberta (sem ninguém online, a regra b não vale).
    """
    relogio = {"agora": 1000.0}
    monkeypatch.setattr(time, "time", lambda: relogio["agora"])

    p = partida()
    p.entrar("Ana", "Beto")
    p.votar("Ana", 0)                                  # Beto online e parado: aberta
    p.sql("UPDATE jogadores SET visto_em = 900 WHERE codigo = ?", (p.codigos["Beto"],))
    login_admin(p)
    relogio["agora"] = 1014.0

    # Avisa quando a requisição entra em banco.transacao, ou seja, quando ela
    # já passou por tudo que vem antes e vai pedir a trava (BEGIN IMMEDIATE).
    chegou_na_trava = threading.Event()
    transacao_original = banco.transacao

    @contextlib.contextmanager
    def transacao_sinalizada(con):
        chegou_na_trava.set()
        with transacao_original(con):
            yield con

    resposta = {}

    def polling_do_admin():
        resposta["status"] = p.cliente.get(f"/admin/api/estado/{p.id}").status_code

    # Outra conexão segura a trava de escrita, como uma requisição demorada.
    outra = banco.conectar(p.app.config["DB_PATH"])
    outra.execute("BEGIN IMMEDIATE")
    thread = threading.Thread(target=polling_do_admin)
    try:
        monkeypatch.setattr(banco, "transacao", transacao_sinalizada)
        thread.start()
        assert chegou_na_trava.wait(timeout=5), "o polling não chegou à trava"
        relogio["agora"] = 1016.0       # enquanto espera, a Ana passa dos 15 s
    finally:
        outra.execute("ROLLBACK")
        outra.close()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert resposta["status"] == 200
    assert p.fase() == ("votacao", 1)

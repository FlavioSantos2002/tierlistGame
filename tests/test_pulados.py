"""Investigação da v2: quando uma rodada ao vivo pode fechar com ZERO votos.

Pela especificação, só em dois casos:
  1. todos os jogadores online realmente pularam; ou
  2. o admin forçou o avanço.
Estes testes procuram qualquer outro caminho: a regra em todas as combinações,
cenários aleatórios pela API (presença expirando, polling do admin, jogadores
sumindo e voltando) e requisições chegando ao mesmo tempo.
"""
import itertools
import random
import time

from jogo import pode_fechar_votacao
from test_concorrencia import ao_mesmo_tempo
from test_fluxo import login_admin

# ----- 1. A regra, em todas as combinações (3 jogadores) -----

PRESENCAS = ("online", "offline")
ACOES = ("nada", "votou", "pulou")


def test_regra_so_fecha_sem_votos_se_todos_os_online_pularam():
    jogadores = (1, 2, 3)
    fechamentos_sem_voto = 0
    for combinacao in itertools.product(itertools.product(PRESENCAS, ACOES), repeat=3):
        online = {j for j, (presenca, _) in zip(jogadores, combinacao) if presenca == "online"}
        votaram = {j for j, (_, acao) in zip(jogadores, combinacao) if acao == "votou"}
        pularam = {j for j, (_, acao) in zip(jogadores, combinacao) if acao == "pulou"}
        if pode_fechar_votacao(jogadores, online, votaram, pularam) and not votaram:
            fechamentos_sem_voto += 1
            assert online, combinacao
            assert online <= pularam, combinacao
    assert fechamentos_sem_voto > 0          # o caso permitido existe e foi visto


# ----- 2. Cenários aleatórios pela API, com relógio controlado -----

def conferir_fechamento(p, rodada, agora, motivo):
    """Se a rodada fechou sem votos, confere que foi pelo caso permitido."""
    item = p.item(rodada)
    if item["situacao"] != "pulado":
        return False
    linhas = p.sql(
        "SELECT j.visto_em, j.removido_em, v.faixa_indice, v.jogador_id FROM jogadores j"
        " LEFT JOIN votos v ON v.jogador_id = j.id"
        "   AND v.item_id = (SELECT id FROM itens WHERE partida_id = ? AND rodada = ?)"
        " WHERE j.partida_id = ?",
        (p.id, rodada, p.id),
    )
    ativos = [l for l in linhas if l["removido_em"] is None]
    online = [l for l in ativos if l["visto_em"] is not None and l["visto_em"] >= agora - 15]
    assert all(l["faixa_indice"] is None for l in ativos), motivo
    assert online, f"fechou sem votos e sem ninguém online ({motivo})"
    assert all(l["jogador_id"] is not None for l in online), \
        f"fechou sem votos com alguém online que não pulou ({motivo})"
    return True


def test_cenarios_aleatorios_nunca_fecham_sem_votos_por_outro_caminho(partida, monkeypatch):
    relogio = {"agora": 1000.0}
    monkeypatch.setattr(time, "time", lambda: relogio["agora"])
    sorteio = random.Random(2026)             # semente fixa: o teste é sempre o mesmo
    nomes = ("Ana", "Beto", "Caio")
    fechamentos_sem_voto = 0

    for cenario in range(40):
        p = partida(rodadas=3)
        login_admin(p)
        for passo in range(30):
            estado_antes, rodada_antes = p.fase()
            if estado_antes == "encerrada":
                break
            nome = sorteio.choice(nomes)
            acao = sorteio.choice(
                ["polling", "polling", "votar", "pular", "continuar", "sumir", "tempo", "admin"]
            )
            if acao == "polling":
                p.estado(nome)
            elif acao == "votar":
                p.acao("votar", nome, rodada=rodada_antes, faixa=sorteio.randrange(5),
                       revisao=p.revisao(nome))
            elif acao == "pular":
                p.acao("pular", nome, rodada=rodada_antes, revisao=p.revisao(nome))
            elif acao == "continuar":
                p.acao("continuar", nome, rodada=rodada_antes)
            elif acao == "sumir":
                p.sql("UPDATE jogadores SET visto_em = ? WHERE codigo = ?",
                      (relogio["agora"] - 100, p.codigos[nome]))
            elif acao == "tempo":
                relogio["agora"] += sorteio.choice([1, 5, 10, 16])
            else:
                p.cliente.get(f"/admin/api/estado/{p.id}")

            estado_depois, rodada_depois = p.fase()
            if estado_antes == "votacao" and (estado_depois, rodada_depois) != (estado_antes, rodada_antes):
                motivo = f"cenário {cenario}, passo {passo}, {nome} {acao}"
                if conferir_fechamento(p, rodada_antes, relogio["agora"], motivo):
                    fechamentos_sem_voto += 1
            relogio["agora"] += 0.5
    # Os cenários passaram pelo caso permitido (todos os online pularam), então
    # a conferência acima foi exercitada de verdade.
    assert fechamentos_sem_voto > 0


# ----- 3. Requisições ao mesmo tempo -----

def test_pulos_e_voto_simultaneos_nunca_fecham_sem_o_voto(partida):
    # Ana e Beto pulam enquanto o Caio vota, tudo ao mesmo tempo. Seja qual for
    # a ordem em que o servidor processar, a rodada só pode fechar COM o voto
    # do Caio (enquanto ele não agiu, ele está online e trava a regra b).
    for _ in range(15):
        p = partida()
        p.entrar("Ana", "Beto", "Caio")

        def pedido(tipo, nome, **corpo):
            cliente = p.app.test_client()
            return lambda: cliente.post(
                f"/api/{tipo}/{p.codigos[nome]}", json=dict(rodada=1, revisao=0, **corpo)
            ).status_code

        status = ao_mesmo_tempo([pedido("pular", "Ana"), pedido("pular", "Beto"),
                                 pedido("votar", "Caio", faixa=2)])
        assert status == [200, 200, 200]
        assert p.fase() == ("resultado", 1)
        assert p.item(1)["situacao"] == "classificado"
        assert p.item(1)["faixa_indice"] == 2


def test_pulos_simultaneos_com_alguem_online_parado_nao_fecham(partida):
    for _ in range(10):
        p = partida()
        p.entrar("Ana", "Beto", "Caio")

        def pular(nome):
            cliente = p.app.test_client()
            return lambda: cliente.post(
                f"/api/pular/{p.codigos[nome]}", json={"rodada": 1, "revisao": 0}
            ).status_code

        def polling(nome):
            cliente = p.app.test_client()
            return lambda: cliente.get(f"/api/estado/{p.codigos[nome]}").status_code

        assert ao_mesmo_tempo([pular("Ana"), pular("Beto"), polling("Caio")]) == [200] * 3
        assert p.fase() == ("votacao", 1)          # o Caio está online e não agiu


# ----- 4. O admin forçando -----

def test_forcar_so_fecha_a_fase_que_o_admin_estava_vendo(partida):
    # O caminho provável dos pulados do teste da v1: o admin quer sair do
    # resultado, mas a partida já passou sozinha para a votação seguinte. Com a
    # fase esperada no formulário, o clique "atrasado" não fecha a votação nova.
    p = partida(rodadas=2)
    p.entrar("Ana", "Beto")
    token = login_admin(p)
    p.votar("Ana", 1)
    p.votar("Beto", 1)
    p.continuar("Ana")
    p.continuar("Beto")
    assert p.fase() == ("votacao", 2)              # avançou sozinha
    # O formulário ainda estava com a fase que o admin viu (resultado da rodada 1).
    p.cliente.post(f"/admin/partida/{p.id}/forcar",
                   data={"csrf_token": token, "estado": "resultado", "rodada": "1"})
    assert p.fase() == ("votacao", 2)              # nada foi fechado
    assert p.item(2)["situacao"] == "pendente"


def test_botao_de_forcar_diz_o_que_vai_acontecer(partida):
    p = partida(rodadas=2)
    login_admin(p)
    p.cliente.application.config["BASE_URL"] = "http://teste"   # não consulta o túnel
    try:
        html = p.cliente.get(f"/admin/partida/{p.id}").get_data(as_text=True)
        assert "Fechar a votação agora" in html
        assert "Se ninguém tiver votado, o item vai para os pulados." in html
    finally:
        p.cliente.application.config["BASE_URL"] = ""

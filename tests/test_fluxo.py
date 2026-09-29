"""Fluxo da partida pela API, com jogadores online e offline.

Lembrete ao ler os cenários: quem nunca fez polling (p.entrar) conta como
offline. Então, se só a Ana entrou, o voto dela já fecha a rodada (regra b).
"""
import json
import re


# ----- Espera e início -----

def test_espera_mostra_quem_ja_entrou(partida):
    p = partida(iniciar=False)
    p.entrar("Ana", "Beto")
    dados = p.estado("Ana").get_json()
    assert dados["estado"] == "espera"
    assert dados["entraram"] == ["Ana", "Beto"]
    assert dados["eu"]["nome"] == "Ana"


def test_espera_nao_avanca_sozinha(partida):
    p = partida(iniciar=False)
    p.entrar("Ana", "Beto", "Caio")
    assert p.fase() == ("espera", 0)


# ----- Fechamento da votação -----

def test_fecha_quando_todos_votam(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 0)
    p.votar("Beto", 1)
    assert p.fase() == ("votacao", 1)
    p.votar("Caio", 2)
    assert p.fase() == ("resultado", 1)
    assert p.item(1)["faixa_indice"] == 2          # 1 voto em cada: empate -> pior (B)


def test_jogador_que_nunca_entrou_nao_trava(partida):
    p = partida()
    p.entrar("Ana", "Beto")                        # Caio nunca abriu o link
    p.votar("Ana", 0)
    assert p.fase() == ("votacao", 1)              # Beto online ainda não votou
    p.votar("Beto", 1)
    assert p.fase() == ("resultado", 1)
    dados = p.estado("Ana").get_json()
    assert dados["distribuicao"] == [1, 1, 0, 0, 0]   # os dois votos contaram
    assert p.item(1)["faixa_indice"] == 1          # empate entre S e A -> pior (A)


def test_online_parado_trava_ate_ficar_offline(partida):
    p = partida()
    p.entrar("Caio")
    p.votar("Ana", 2)
    p.votar("Beto", 2)
    assert p.fase() == ("votacao", 1)              # Caio está online e não votou
    p.deixar_offline("Caio")
    p.estado("Ana")                                # o polling percebe e fecha
    assert p.fase() == ("resultado", 1)


def test_offline_que_volta_pode_votar(partida):
    p = partida()
    p.entrar("Beto", "Caio")
    p.votar("Ana", 0)
    p.deixar_offline("Caio")
    assert p.fase() == ("votacao", 1)              # Beto (online) ainda não votou
    p.votar("Caio", 4)                             # Caio voltou antes de fechar
    p.votar("Beto", 4)
    assert p.item(1)["faixa_indice"] == 4          # 2 votos em D, 1 em S -> D


def test_ninguem_online_nao_fecha(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 0)
    p.deixar_offline("Ana", "Beto", "Caio")
    login_admin(p)
    p.cliente.get(f"/admin/api/estado/{p.id}")     # polling do admin também verifica
    assert p.fase() == ("votacao", 1)


def test_todos_votaram_fecha_mesmo_offline(partida):
    # Votação aberta com os votos de todos já gravados e ninguém online:
    # a regra (a) fecha no próximo polling, mesmo sem ninguém online.
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 0)
    p.votar("Beto", 2)
    assert p.fase() == ("votacao", 1)              # Caio online e parado
    p.deixar_offline("Ana", "Beto", "Caio")
    # O voto do Caio entra direto no banco, sem passar pela verificação.
    p.sql(
        "INSERT INTO votos (item_id, jogador_id, faixa_indice, votado_em)"
        " SELECT i.id, j.id, 4, 0 FROM itens i, jogadores j"
        " WHERE i.partida_id = ? AND i.rodada = 1 AND j.codigo = ?",
        (p.id, p.codigos["Caio"]),
    )
    assert p.fase() == ("votacao", 1)
    login_admin(p)
    resposta = p.cliente.get(f"/admin/api/estado/{p.id}")
    assert resposta.status_code == 200
    assert p.fase() == ("resultado", 1)
    assert resposta.get_json()["distribuicao"] == [1, 0, 1, 0, 1]
    assert p.item(1)["faixa_indice"] == 4          # 1 voto em cada: empate -> pior (D)


# ----- Pular -----

def test_pular_conta_para_fechar(partida):
    p = partida()
    p.entrar("Caio")
    p.votar("Ana", 3)
    p.pular("Beto")
    p.pular("Caio")
    assert p.fase() == ("resultado", 1)
    assert p.item(1)["faixa_indice"] == 3          # as duas abstenções não contam


def test_todos_pulam_item_fica_fora(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    for nome in ("Ana", "Beto", "Caio"):
        p.pular(nome)
    assert p.fase() == ("resultado", 1)
    assert p.item(1)["situacao"] == "pulado"
    dados = p.estado("Ana").get_json()
    # Os itens são sorteados, então conferimos o item pelo que a própria API mostrou.
    assert dados["pulados"] == [dict(dados["item"], novo=True)]
    assert all(faixa == [] for faixa in dados["tier_list"])


def test_pulou_e_depois_votou(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.pular("Ana")
    resposta = p.votar("Ana", 2)
    assert resposta.status_code == 200
    assert resposta.get_json()["eu"] == {
        "nome": "Ana", "voto": 2, "pulou": False, "continuou": False, "revisao": 2,
    }


def test_nao_pode_pular_depois_de_votar(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 2)
    resposta = p.pular("Ana", esperado=409)
    assert resposta.get_json()["estado"]["eu"]["voto"] == 2    # o voto continua lá


def test_trocar_voto(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 0)
    p.votar("Ana", 4)
    assert p.estado("Ana").get_json()["eu"]["voto"] == 4
    p.votar("Beto", 4)
    p.votar("Caio", 4)
    assert p.item(1)["faixa_indice"] == 4


# ----- Resultado e avanço -----

def test_continuar_avanca_quando_todos_online_continuam(partida):
    p = partida(rodadas=2)
    p.entrar("Ana", "Beto", "Caio")
    for nome in ("Ana", "Beto", "Caio"):
        p.votar(nome, 1)
    p.deixar_offline("Caio")
    p.continuar("Ana")
    assert p.fase() == ("resultado", 1)            # Beto ainda não continuou
    p.continuar("Beto")
    assert p.fase() == ("votacao", 2)              # Caio offline não trava
    assert p.item(2)["situacao"] == "pendente"


def test_ultima_rodada_encerra(partida):
    p = partida(jogadores=("Ana", "Beto"), rodadas=1)
    p.entrar("Ana", "Beto")
    p.votar("Ana", 0)
    p.votar("Beto", 0)
    p.continuar("Ana")
    p.continuar("Beto")
    assert p.fase() == ("encerrada", 1)
    dados = p.estado("Ana").get_json()
    assert dados["item"] is None
    assert dados["tier_list"][0] == [{"nome": "Item 0", "imagem": "https://x/0.png", "novo": False}]


def test_resultado_sem_ninguem_online_nao_avanca(partida):
    p = partida(jogadores=("Ana", "Beto"))
    p.entrar("Ana", "Beto")
    p.votar("Ana", 0)
    p.votar("Beto", 0)
    p.deixar_offline("Ana", "Beto")
    login_admin(p)
    p.cliente.get(f"/admin/api/estado/{p.id}")
    assert p.fase() == ("resultado", 1)


def test_resultado_mostra_distribuicao_e_destaque(partida):
    p = partida()
    p.entrar("Caio")
    p.votar("Ana", 0)
    p.votar("Beto", 1)
    p.pular("Caio")
    dados = p.estado("Ana").get_json()
    assert dados["estado"] == "resultado"
    assert dados["distribuicao"] == [1, 1, 0, 0, 0]
    assert dados["abstencoes"] == 1
    assert dados["tier_list"][1][0]["novo"] is True      # empate S/A -> A


# ----- Pedidos inválidos -----

def test_voto_em_rodada_antiga_e_recusado(partida):
    p = partida()
    resposta = p.votar("Ana", 0, rodada=2, esperado=409)
    assert resposta.get_json()["estado"]["rodada"] == 1


def test_continuar_na_votacao_e_recusado(partida):
    p = partida()
    p.continuar("Ana", esperado=409)


def test_post_sem_json_e_recusado(partida):
    p = partida()
    resposta = p.cliente.post(f"/api/votar/{p.codigos['Ana']}", data={"rodada": 1, "faixa": 0})
    assert resposta.status_code == 415


def test_faixa_invalida(partida):
    p = partida(faixas=5)
    p.votar("Ana", 5, esperado=400)
    p.votar("Ana", -1, esperado=400)
    assert p.acao("votar", "Ana", rodada=1, faixa=True, revisao=0).status_code == 400
    assert p.acao("votar", "Ana", rodada=1, faixa="0", revisao=0).status_code == 400


def test_votar_e_pular_exigem_revisao(partida):
    p = partida()
    assert p.acao("votar", "Ana", rodada=1, faixa=0).status_code == 400
    assert p.acao("pular", "Ana", rodada=1).status_code == 400
    assert p.voto_no_banco("Ana") is None


def test_partida_apagada(partida):
    p = partida()
    p.sql("DELETE FROM partidas WHERE id = ?", (p.id,))
    resposta = p.estado("Ana")
    assert resposta.status_code == 404
    assert resposta.get_json()["apagada"] is True
    p.votar("Ana", 0, rodada=1, revisao=0, esperado=404)


# ----- Anonimato e versão -----

def test_jogador_nao_ve_voto_nem_nome_dos_outros(partida):
    p = partida()
    p.entrar("Caio")
    p.votar("Beto", 3)
    texto = json.dumps(p.estado("Ana").get_json())
    assert "Beto" not in texto and "Caio" not in texto
    assert "jogadores" not in p.estado("Ana").get_json()   # lista de online é só do admin
    p.votar("Ana", 0)
    p.votar("Caio", 0)
    texto = json.dumps(p.estado("Ana").get_json())           # resultado: só contagens
    assert "Beto" not in texto and "Caio" not in texto


def test_versao_muda_so_quando_algo_muda(partida):
    p = partida()
    p.entrar("Ana", "Beto")
    v1 = p.estado("Ana").get_json()["versao"]
    assert p.estado("Ana").get_json()["versao"] == v1      # nada mudou
    p.votar("Beto", 0)
    v2 = p.estado("Ana").get_json()["versao"]
    assert v2 != v1                                        # voto
    p.deixar_offline("Beto")
    assert p.estado("Ana").get_json()["versao"] != v2      # alguém ficou offline


def test_presenca_faltam_x_de_y(partida):
    p = partida()
    p.entrar("Ana", "Beto")                                # Caio nunca entrou
    p.votar("Ana", 0)
    presenca = p.estado("Ana").get_json()["presenca"]
    assert presenca == {"online": 2, "offline": 1, "faltam": 1}


# ----- Admin -----

def login_admin(p, cliente=None):
    """Faz login no cliente e devolve o token CSRF da sessão nova."""
    cliente = cliente or p.cliente
    padrao = r'name="csrf_token" value="([^"]+)"'
    html = cliente.get("/admin/entrar").get_data(as_text=True)
    token = re.search(padrao, html).group(1)
    cliente.post("/admin/entrar", data={"token": "token-de-teste", "csrf_token": token})
    # O login troca o token CSRF; pegamos o novo numa página do painel.
    html = cliente.get("/admin/").get_data(as_text=True)
    return re.search(padrao, html).group(1)


def test_admin_api_exige_login(partida):
    p = partida()
    resposta = p.cliente.get(f"/admin/api/estado/{p.id}")
    assert resposta.status_code == 401


def test_admin_ve_quem_esta_online_e_quem_agiu(partida):
    p = partida(jogadores=("Ana", "Beto", "Caio", "Davi"))
    p.entrar("Ana", "Beto", "Caio")                        # Davi nunca entrou
    p.votar("Ana", 1)
    p.pular("Beto")
    login_admin(p)
    dados = p.cliente.get(f"/admin/api/estado/{p.id}").get_json()
    assert dados["estado"] == "votacao"                    # Caio online e parado
    assert all(isinstance(j.pop("id"), int) for j in dados["jogadores"])
    assert all(j.pop("removido") is False for j in dados["jogadores"])
    assert dados["jogadores"] == [
        {"nome": "Ana", "entrou": True, "online": True, "acao": "votou"},
        {"nome": "Beto", "entrou": True, "online": True, "acao": "pulou"},
        {"nome": "Caio", "entrou": True, "online": True, "acao": None},
        {"nome": "Davi", "entrou": False, "online": False, "acao": None},
    ]                                  # comparação exata: o admin não vê em quê votaram


def test_iniciar_so_uma_vez(partida):
    p = partida(iniciar=False)
    token = login_admin(p)
    p.cliente.post(f"/admin/partida/{p.id}/iniciar", data={"csrf_token": token})
    assert p.fase() == ("votacao", 1)
    p.cliente.post(f"/admin/partida/{p.id}/iniciar", data={"csrf_token": token})
    assert p.fase() == ("votacao", 1)


def test_forcar_avanco_e_clique_duplicado(partida):
    p = partida(rodadas=2)
    token = login_admin(p)
    dados = {"csrf_token": token, "estado": "votacao", "rodada": "1"}
    p.cliente.post(f"/admin/partida/{p.id}/forcar", data=dados)
    assert p.fase() == ("resultado", 1)
    assert p.item(1)["situacao"] == "pulado"               # ninguém votou
    p.cliente.post(f"/admin/partida/{p.id}/forcar", data=dados)   # clique repetido
    assert p.fase() == ("resultado", 1)                    # não pulou outra fase
    dados["estado"] = "resultado"
    p.cliente.post(f"/admin/partida/{p.id}/forcar", data=dados)
    assert p.fase() == ("votacao", 2)


def test_forcar_exige_csrf(partida):
    p = partida()
    login_admin(p)
    resposta = p.cliente.post(f"/admin/partida/{p.id}/forcar", data={"estado": "votacao", "rodada": "1"})
    assert resposta.status_code == 400
    assert p.fase() == ("votacao", 1)


# ----- Revisão do voto: envio antigo chegando atrasado ao servidor -----
#
# Cenário do parecer: o jogador vota S; o pedido demora e o navegador desiste
# (tempo esgotado); ele vota A, e o A é aceito; SÓ ENTÃO o pedido do S chega
# ao servidor. Os dois saíram com a mesma revisão (a tela não tinha mudado),
# então o S chega "velho" e tem de ser recusado: o A continua valendo.

def test_voto_atrasado_nao_desfaz_escolha_mais_nova(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    assert p.estado("Ana").get_json()["eu"]["revisao"] == 0
    # (o envio do S, com revisão 0, está "na rede" e ainda não chegou)
    resposta = p.votar("Ana", 1, revisao=0)                 # A: chega e é aceito
    assert resposta.get_json()["eu"]["voto"] == 1
    assert resposta.get_json()["eu"]["revisao"] == 1
    resposta = p.votar("Ana", 0, revisao=0, esperado=409)   # S chega atrasado
    assert resposta.get_json()["estado"]["eu"]["voto"] == 1  # a tela recebe o A
    assert p.voto_no_banco("Ana") == (1, 1)                  # e o banco mantém o A


def test_trocar_voto_com_a_revisao_certa(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 0, revisao=0)
    p.votar("Ana", 3, revisao=1)
    assert p.voto_no_banco("Ana") == (3, 2)


def test_pulo_atrasado_nao_desfaz_voto(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 2, revisao=0)
    p.pular("Ana", revisao=0, esperado=409)                  # pulo antigo chega depois
    assert p.voto_no_banco("Ana") == (2, 1)


def test_voto_atrasado_nao_desfaz_pulo(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.pular("Ana", revisao=0)                                # abstenção aceita
    p.votar("Ana", 0, revisao=0, esperado=409)               # voto antigo chega depois
    assert p.voto_no_banco("Ana") == (None, 1)
    assert p.estado("Ana").get_json()["eu"]["pulou"] is True


def test_voto_atrasado_de_rodada_anterior_e_recusado(partida):
    # O envio atrasado pode chegar até depois de a rodada fechar.
    p = partida(rodadas=2)
    p.entrar("Ana", "Beto", "Caio")
    for nome in ("Ana", "Beto", "Caio"):
        p.votar(nome, 1)
    for nome in ("Ana", "Beto", "Caio"):
        p.continuar(nome)
    assert p.fase() == ("votacao", 2)
    p.votar("Ana", 0, rodada=1, revisao=0, esperado=409)
    assert p.item(1)["faixa_indice"] == 1
    assert p.voto_no_banco("Ana") is None                    # nada gravado na rodada 2

"""Modo individual ("cada um no seu ritmo"): regras, API e visibilidade."""
import json
import random

from individual import compatibilidade, tier_geral
from test_concorrencia import ao_mesmo_tempo
from test_fluxo import login_admin
from test_remover import mensagem_do_admin, remover


# ===========================================================================
# Compatibilidade (regra pura), com 5 faixas: 0 = S ... 4 = D
# ===========================================================================

def test_compatibilidade_tudo_igual():
    assert compatibilidade({1: 0, 2: 3, 3: 4}, {1: 0, 2: 3, 3: 4}, 5) == 100


def test_compatibilidade_tudo_no_extremo_oposto():
    assert compatibilidade({1: 0, 2: 4}, {1: 4, 2: 0}, 5) == 0


def test_compatibilidade_diferencas_mistas():
    # diferenças 0, 1 e 2 -> notas 1; 0,75; 0,5 -> média 0,75
    assert compatibilidade({1: 0, 2: 1, 3: 2}, {1: 0, 2: 2, 3: 4}, 5) == 75


def test_compatibilidade_ignora_pulados_dos_dois_lados():
    minhas = {1: 0, 2: None, 3: 2}          # eu pulei o 2
    geral = {1: 0, 2: 4, 3: None}           # a geral mandou o 3 para "pulados"
    assert compatibilidade(minhas, geral, 5) == 100     # só o item 1 conta


def test_compatibilidade_sem_item_em_comum():
    assert compatibilidade({1: None, 2: None}, {1: 3, 2: 0}, 5) is None
    assert compatibilidade({1: 2}, {1: None}, 5) is None
    assert compatibilidade({}, {}, 5) is None


def test_compatibilidade_arredonda_para_o_inteiro_mais_proximo():
    assert compatibilidade({1: 0, 2: 0}, {1: 0, 2: 1}, 5) == 88     # 87,5 -> 88
    # 62,5 -> 63 (o round() do Python daria 62: arredonda o ,5 para o par)
    assert compatibilidade({1: 0, 2: 0, 3: 0, 4: 0}, {1: 0, 2: 1, 3: 2, 4: 3}, 5) == 63
    assert compatibilidade({1: 0, 2: 0, 3: 0}, {1: 0, 2: 1, 3: 1}, 3) == 67   # 66,67 -> 67
    assert compatibilidade({1: 0}, {1: 1}, 2) == 0                   # 2 faixas: 1 de diferença = 0


def test_tier_geral_pela_maioria_sem_contar_pulos():
    respostas = {
        10: {1: 0, 2: None, 3: 1},
        11: {1: 0, 2: None, 3: 2},
    }
    assert tier_geral(respostas, [1, 2, 3]) == {1: 0, 2: None, 3: 2}   # 3: empate -> pior


# ===========================================================================
# Criação e ordem
# ===========================================================================

def individual(partida, **kwargs):
    kwargs.setdefault("rodadas", 4)
    return partida(modo="individual", **kwargs)


def itens_da_partida(p):
    return [l["id"] for l in p.sql(
        "SELECT id FROM itens WHERE partida_id = ? ORDER BY rodada", (p.id,))]


def test_nasce_aberta_e_sem_iniciar(partida):
    p = individual(partida)
    assert p.fase() == ("aberta", 0)
    token = login_admin(p)
    p.cliente.post(f"/admin/partida/{p.id}/iniciar", data={"csrf_token": token})
    assert p.fase() == ("aberta", 0)                     # "Iniciar" não existe aqui
    p.cliente.post(f"/admin/partida/{p.id}/forcar",
                   data={"csrf_token": token, "estado": "aberta", "rodada": "0"})
    assert p.fase() == ("aberta", 0)                     # nem "Forçar avanço"


def test_mesmos_itens_com_ordem_sorteada_e_fixa_por_jogador(partida):
    random.seed(7)
    p = individual(partida, rodadas=6)
    itens = sorted(itens_da_partida(p))
    ordens = {nome: p.ordem(nome) for nome in ("Ana", "Beto", "Caio")}
    for ordem in ordens.values():
        assert sorted(ordem) == itens                    # os mesmos itens para todos
    assert len({tuple(o) for o in ordens.values()}) > 1  # mas em ordens diferentes
    # A ordem vem do banco: é a mesma a cada consulta (recarregar, outro dia...).
    na_tela = [i["id"] for i in p.estado("Ana").get_json()["itens"]]
    assert na_tela == ordens["Ana"]
    assert [i["id"] for i in p.estado("Ana").get_json()["itens"]] == na_tela


# ===========================================================================
# Preenchimento
# ===========================================================================

def test_cada_resposta_e_salva_na_hora_e_retoma_de_onde_parou(partida):
    p = individual(partida)
    ordem = p.ordem("Ana")
    p.responder("Ana", ordem[0], 1)
    p.responder("Ana", ordem[1], None)                   # pulou
    # Outro "celular" (cliente novo) abre o mesmo link depois:
    dados = p.app.test_client().get(f"/api/estado/{p.codigos['Ana']}").get_json()
    assert dados["eu"]["respondidos"] == 2
    itens = dados["itens"]
    assert [(i["respondido"], i["faixa"]) for i in itens] == [
        (True, 1), (True, None), (False, None), (False, None)]


def test_voltar_e_trocar_a_resposta(partida):
    p = individual(partida)
    item = p.ordem("Ana")[0]
    p.responder("Ana", item, 0)
    p.responder("Ana", item, 3)                          # voltou e trocou
    p.responder("Ana", item, None)                       # trocou por "pular"
    p.responder("Ana", item, 2)                          # e voltou a classificar
    resposta = p.estado("Ana").get_json()["itens"][0]
    assert (resposta["faixa"], resposta["revisao"]) == (2, 4)


def test_resposta_com_revisao_antiga_e_recusada(partida):
    p = individual(partida)
    item = p.ordem("Ana")[0]
    p.responder("Ana", item, 1, revisao=0)
    resposta = p.responder("Ana", item, 4, revisao=0, esperado=409)   # envio atrasado
    assert resposta.get_json()["estado"]["itens"][0]["faixa"] == 1


def test_dados_invalidos(partida):
    p = individual(partida)
    outra = individual(partida, jogadores=("Zeca", "Yara"))
    item = p.ordem("Ana")[0]
    p.responder("Ana", outra.ordem("Zeca")[0], 1, revisao=0, esperado=400)   # item de outra partida
    p.responder("Ana", item, 5, revisao=0, esperado=400)                     # faixa inexistente
    sem_faixa = p.acao("responder", "Ana", item=item, revisao=0)
    assert sem_faixa.status_code == 400                                      # sem o campo "faixa"
    assert p.estado("Ana").get_json()["eu"]["respondidos"] == 0


def test_finalizar_exige_todos_os_itens_respondidos(partida):
    p = individual(partida)
    ordem = p.ordem("Ana")
    for item in ordem[:-1]:
        p.responder("Ana", item, 0)
    resposta = p.finalizar("Ana", esperado=409)
    assert "falta responder 1" in resposta.get_json()["erro"]
    p.responder("Ana", ordem[-1], None)                  # "pulei" também é resposta
    assert p.finalizar("Ana").get_json()["eu"]["finalizado"] is True


def test_respostas_travadas_depois_de_finalizar(partida):
    p = individual(partida)
    p.responder_tudo("Ana", lambda item: 2)
    p.finalizar("Ana")
    p.responder("Ana", p.ordem("Ana")[0], 0, esperado=409)
    p.finalizar("Ana", esperado=409)
    faixas = [l["faixa_indice"] for l in p.sql(
        "SELECT faixa_indice FROM votos v JOIN jogadores j ON j.id = v.jogador_id"
        " WHERE j.codigo = ?", (p.codigos["Ana"],))]
    assert faixas == [2, 2, 2, 2]


# ===========================================================================
# Visibilidade
# ===========================================================================

def test_quem_nao_finalizou_nao_ve_nada_dos_outros(partida):
    p = individual(partida)
    p.responder_tudo("Beto", lambda item: 0)
    p.finalizar("Beto")
    p.responder("Ana", p.ordem("Ana")[0], 3)
    for resposta in (p.estado("Ana"), p.responder("Ana", p.ordem("Ana")[1], 1)):
        dados = resposta.get_json()
        assert dados["resultado"] is None
        texto = json.dumps(dados)
        assert "Beto" not in texto and "Caio" not in texto          # nem nomes
        assert "geral" not in texto and "outros" not in texto       # nem listas
        assert set(dados) == {"versao", "modo", "estado", "tema", "total_itens",
                              "faixas", "eu", "itens", "resultado"}


def test_versao_do_jogador_so_muda_com_o_que_ele_ve(partida):
    # A versão da partida sobe a cada resposta de qualquer um. Se o jogador
    # recebesse esse número, daria para contar pela API as respostas dos outros.
    p = individual(partida)
    versao = lambda nome: p.estado(nome).get_json()["versao"]
    p.entrar("Ana", "Beto", "Caio")
    antes = versao("Ana")
    p.responder("Beto", p.ordem("Beto")[0], 2)                # outro respondeu
    assert versao("Ana") == antes
    p.responder("Ana", p.ordem("Ana")[0], 1)                  # ela mesma respondeu
    assert versao("Ana") != antes

    # Depois de finalizar: o que ela vê só muda quando alguém finaliza.
    p.responder_tudo("Ana", lambda item: 0)
    p.finalizar("Ana")
    antes = versao("Ana")
    p.responder("Caio", p.ordem("Caio")[0], 3)                # Caio ainda preenchendo
    assert versao("Ana") == antes
    p.responder_tudo("Beto", lambda item: 4)
    p.finalizar("Beto")                                        # entra na geral
    assert versao("Ana") != antes

    # Encerrar muda a tela de todos, inclusive de quem ainda preenchia.
    antes = versao("Caio")
    token = login_admin(p)
    p.cliente.post(f"/admin/partida/{p.id}/encerrar", data={"csrf_token": token})
    assert versao("Caio") != antes


def test_depois_de_finalizar_ve_geral_compatibilidade_e_os_outros(partida):
    p = individual(partida)
    itens = itens_da_partida(p)
    # Ana: tudo S. Beto: S nos dois primeiros, D nos dois últimos.
    p.responder_tudo("Ana", lambda item: 0)
    p.responder_tudo("Beto", lambda item: 0 if item in itens[:2] else 4)
    p.finalizar("Ana")
    p.finalizar("Beto")
    resultado = p.estado("Ana").get_json()["resultado"]
    # Geral: S nos dois primeiros; nos dois últimos, 1 x 1 (empate -> pior: D).
    assert [i["id"] for i in resultado["geral"]["tier_list"][0]] == sorted(itens[:2])
    assert sorted(i["id"] for i in resultado["geral"]["tier_list"][4]) == sorted(itens[2:])
    assert resultado["compatibilidade"] == 50            # 2 itens iguais, 2 no extremo oposto
    assert p.estado("Beto").get_json()["resultado"]["compatibilidade"] == 100
    assert [o["nome"] for o in resultado["outros"]] == ["Beto"]      # sem anonimato
    assert len(resultado["minha"]["tier_list"][0]) == 4
    assert resultado["faltam"] == ["Caio"]


def test_compatibilidade_sem_item_em_comum_vira_traco(partida):
    p = individual(partida)
    p.responder_tudo("Ana", lambda item: None)           # pulou tudo
    p.responder_tudo("Beto", lambda item: 1)
    p.finalizar("Ana")
    p.finalizar("Beto")
    assert p.estado("Ana").get_json()["resultado"]["compatibilidade"] is None


def test_geral_so_usa_quem_finalizou(partida):
    p = individual(partida)
    p.responder_tudo("Ana", lambda item: 1)
    p.responder_tudo("Caio", lambda item: 4)             # respondeu tudo, mas não finalizou
    p.finalizar("Ana")
    geral = p.estado("Ana").get_json()["resultado"]["geral"]
    assert len(geral["tier_list"][1]) == 4 and geral["tier_list"][4] == []


# ===========================================================================
# Encerrar
# ===========================================================================

def test_encerra_sozinha_quando_todos_os_ativos_finalizam(partida):
    p = individual(partida)
    for nome in ("Ana", "Beto"):
        p.responder_tudo(nome, lambda item: 2)
        p.finalizar(nome)
    assert p.fase() == ("aberta", 0)
    p.responder_tudo("Caio", lambda item: 2)
    dados = p.finalizar("Caio").get_json()
    assert dados["estado"] == "encerrada"
    assert dados["resultado"]["faltam"] == []


def test_encerrar_e_revelar_pelo_admin(partida):
    p = individual(partida)
    p.responder_tudo("Ana", lambda item: 0)
    p.finalizar("Ana")
    p.responder("Beto", p.ordem("Beto")[0], 4)           # Beto só começou
    token = login_admin(p)
    p.cliente.post(f"/admin/partida/{p.id}/encerrar", data={"csrf_token": token})
    assert p.fase() == ("encerrada", 0)
    # Quem não finalizou vê os resultados, mas sem lista nem compatibilidade próprias,
    # e as respostas parciais dele não entram na geral.
    resultado = p.estado("Beto").get_json()["resultado"]
    assert resultado["minha"] is None and resultado["compatibilidade"] is None
    assert [o["nome"] for o in resultado["outros"]] == ["Ana"]
    assert len(resultado["geral"]["tier_list"][0]) == 4 and resultado["geral"]["tier_list"][4] == []
    p.responder("Beto", p.ordem("Beto")[1], 1, esperado=409)          # travado
    # Clicar de novo não faz nada.
    p.cliente.post(f"/admin/partida/{p.id}/encerrar", data={"csrf_token": token})
    assert "Nada foi feito" in mensagem_do_admin(p)


def test_encerrar_sem_ninguem_finalizar_deixa_resultado_vazio(partida):
    p = individual(partida)
    token = login_admin(p)
    p.cliente.post(f"/admin/partida/{p.id}/encerrar", data={"csrf_token": token})
    resultado = p.estado("Ana").get_json()["resultado"]
    assert resultado["geral"] is None and resultado["outros"] == []


def test_encerrar_nao_vale_para_o_modo_ao_vivo(partida):
    p = partida()
    token = login_admin(p)
    p.cliente.post(f"/admin/partida/{p.id}/encerrar", data={"csrf_token": token})
    assert p.fase() == ("votacao", 1)


def test_finalizar_ao_mesmo_tempo_encerra_uma_vez(partida):
    for _ in range(5):
        p = individual(partida)
        for nome in ("Ana", "Beto", "Caio"):
            p.responder_tudo(nome, lambda item: 1)
        versao_antes = p.sql("SELECT versao FROM partidas WHERE id = ?", (p.id,))[0]["versao"]

        def finalizar(nome):
            cliente = p.app.test_client()
            return lambda: cliente.post(f"/api/finalizar/{p.codigos[nome]}", json={}).status_code

        assert ao_mesmo_tempo([finalizar(n) for n in ("Ana", "Beto", "Caio")]) == [200] * 3
        assert p.fase() == ("encerrada", 0)
        versao_depois = p.sql("SELECT versao FROM partidas WHERE id = ?", (p.id,))[0]["versao"]
        assert versao_depois == versao_antes + 3 + 1     # 3 finalizações + 1 encerramento


# ===========================================================================
# Remover jogador no modo individual
# ===========================================================================

def test_remover_quem_faltava_encerra(partida):
    p = individual(partida)
    for nome in ("Ana", "Beto"):
        p.responder_tudo(nome, lambda item: 2)
        p.finalizar(nome)
    token = login_admin(p)
    remover(p, "Caio", token)
    assert p.fase() == ("encerrada", 0)


def test_respostas_do_removido_saem_da_geral_e_da_lista_dos_outros(partida):
    p = individual(partida)
    p.responder_tudo("Ana", lambda item: 0)
    p.responder_tudo("Beto", lambda item: 4)
    p.finalizar("Ana")
    p.finalizar("Beto")
    geral = p.estado("Ana").get_json()["resultado"]["geral"]
    assert len(geral["tier_list"][4]) == 4               # 1 x 1 em cada item: empate -> D
    token = login_admin(p)
    remover(p, "Beto", token)
    resultado = p.estado("Ana").get_json()["resultado"]
    assert len(resultado["geral"]["tier_list"][0]) == 4  # sem o Beto, fica a Ana
    assert resultado["outros"] == []
    assert resultado["compatibilidade"] == 100
    assert p.estado("Beto").status_code == 403
    p.responder("Beto", p.ordem("Beto")[0], 1, esperado=403)


def test_nao_remove_depois_que_a_partida_terminou(partida):
    p = individual(partida)
    token = login_admin(p)
    p.cliente.post(f"/admin/partida/{p.id}/encerrar", data={"csrf_token": token})
    assert "já terminou" in remover(p, "Ana", token)
    assert p.sql("SELECT removido_em FROM jogadores WHERE codigo = ?",
                 (p.codigos["Ana"],))[0]["removido_em"] is None


# ===========================================================================
# Modos não se misturam
# ===========================================================================

def test_acoes_de_um_modo_sao_recusadas_no_outro(partida):
    ind = individual(partida)
    ao_vivo = partida()
    ind.votar("Ana", 0, rodada=0, revisao=0, esperado=409)
    ind.pular("Ana", rodada=0, revisao=0, esperado=409)
    ind.continuar("Ana", rodada=0, esperado=409)
    item = itens_da_partida(ao_vivo)[0]
    resposta = ao_vivo.responder("Ana", item, 0, revisao=0, esperado=409)
    assert "modo individual" in resposta.get_json()["erro"]
    ao_vivo.finalizar("Ana", esperado=409)


# ===========================================================================
# Admin
# ===========================================================================

def test_admin_ve_progresso_listas_e_geral(partida):
    p = individual(partida)
    p.responder_tudo("Ana", lambda item: 0)
    p.finalizar("Ana")
    p.responder("Beto", p.ordem("Beto")[0], 3)
    p.estado("Caio")                                      # Caio só abriu o link
    token = login_admin(p)
    remover(p, "Caio", token)
    dados = p.cliente.get(f"/admin/api/estado/{p.id}").get_json()
    assert dados["modo"] == "individual" and dados["estado"] == "aberta"
    progresso = {j["nome"]: (j["respondidos"], j["finalizado"], j["removido"])
                 for j in dados["jogadores"]}
    assert progresso == {"Ana": (4, True, False), "Beto": (1, False, False), "Caio": (0, False, True)}
    listas = {j["nome"]: j["lista"] for j in dados["jogadores"]}
    assert len(listas["Beto"]["tier_list"][3]) == 1      # o admin vê até a lista parcial
    assert listas["Caio"] is None
    assert len(dados["geral"]["tier_list"][0]) == 4      # geral: só a Ana finalizou

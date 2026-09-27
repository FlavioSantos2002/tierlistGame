"""Regras puras: cálculo da faixa e condições de fechamento/avanço."""
from jogo import calcular_faixa, ids_online, pode_avancar_resultado, pode_fechar_votacao


# ----- Cálculo da faixa -----

def test_voto_unico():
    assert calcular_faixa([0]) == 0
    assert calcular_faixa([4]) == 4


def test_media_inteira():
    assert calcular_faixa([1, 3]) == 2


def test_arredonda_para_o_mais_proximo():
    assert calcular_faixa([0, 0, 1]) == 0      # 0,33
    assert calcular_faixa([0, 1, 1]) == 1      # 0,67
    assert calcular_faixa([1, 2, 2, 2]) == 2   # 1,75
    assert calcular_faixa([1, 1, 1, 2]) == 1   # 1,25


def test_empate_em_meio_vai_para_a_faixa_melhor():
    assert calcular_faixa([0, 1]) == 0         # 0,5 -> 0
    assert calcular_faixa([1, 2]) == 1         # 1,5 -> 1
    assert calcular_faixa([0, 3]) == 1         # 1,5 -> 1
    assert calcular_faixa([2, 3]) == 2         # 2,5 -> 2
    assert calcular_faixa([0, 1, 2, 3]) == 1   # 1,5 -> 1
    assert calcular_faixa([3, 4]) == 3         # 3,5 -> 3


def test_empate_com_muitos_votos_sem_erro_de_arredondamento():
    # 20 votos com média exatamente 2,5: com float poderia escapar para 3.
    assert calcular_faixa([2] * 10 + [3] * 10) == 2


def test_sem_votos_fica_pulado():
    assert calcular_faixa([]) is None


# ----- Fechamento da votação -----

TODOS = {1, 2, 3}


def test_fecha_quando_todos_votaram_mesmo_offline():
    # Regra (a): vale mesmo sem ninguém online.
    assert pode_fechar_votacao(TODOS, set(), {1, 2, 3}, set())


def test_pular_nao_conta_para_a_regra_de_todos_votaram():
    # 1 e 2 votaram, 3 pulou e está offline; ninguém online -> não fecha.
    assert not pode_fechar_votacao(TODOS, set(), {1, 2}, {3})


def test_fecha_quando_todos_online_votaram_ou_pularam():
    # Regra (b): 3 está offline e não votou; 1 votou e 2 pulou.
    assert pode_fechar_votacao(TODOS, {1, 2}, {1}, {2})


def test_nao_fecha_se_algum_online_nao_agiu():
    assert not pode_fechar_votacao(TODOS, {1, 2, 3}, {1, 2}, set())


def test_nao_fecha_com_ninguem_online():
    # Sem ninguém online, a regra (b) não vale (decisão do dono).
    assert not pode_fechar_votacao(TODOS, set(), {1}, set())
    assert not pode_fechar_votacao(TODOS, set(), set(), set())


# ----- Avanço do resultado -----

def test_avanca_quando_todos_online_continuaram():
    assert pode_avancar_resultado({1, 2}, {1, 2})
    assert pode_avancar_resultado({1}, {1, 3})   # 3 continuou e saiu; tudo bem


def test_nao_avanca_se_algum_online_nao_continuou():
    assert not pode_avancar_resultado({1, 2}, {1})


def test_nao_avanca_com_ninguem_online():
    assert not pode_avancar_resultado(set(), {1, 2, 3})


# ----- Presença -----

def test_online_nos_ultimos_15_segundos():
    agora = 1000.0
    jogadores = [
        {"id": 1, "visto_em": 1000.0},
        {"id": 2, "visto_em": 985.0},    # exatamente 15 s: ainda online
        {"id": 3, "visto_em": 984.9},    # passou de 15 s: offline
        {"id": 4, "visto_em": None},     # nunca entrou
    ]
    assert ids_online(jogadores, agora) == {1, 2}

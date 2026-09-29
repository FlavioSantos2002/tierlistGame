"""Remover jogador (modo ao vivo): regras, rodada liberada, link do removido."""
from test_fluxo import login_admin


def id_do_jogador(p, nome):
    return p.sql("SELECT id FROM jogadores WHERE codigo = ?", (p.codigos[nome],))[0]["id"]


def mensagem_do_admin(p):
    # A lista de partidas mostra o flash e, ao contrário da tela da partida,
    # não consulta o túnel (que nos testes demora ~1 s para recusar no Windows).
    return p.cliente.get("/admin/").get_data(as_text=True)


def remover(p, nome, token, partida_id=None):
    """Clica em "Remover" como o admin. Devolve a página com a mensagem do flash."""
    partida_id = partida_id or p.id
    resposta = p.cliente.post(
        f"/admin/partida/{partida_id}/remover/{id_do_jogador(p, nome)}",
        data={"csrf_token": token},
    )
    assert resposta.status_code == 302
    return mensagem_do_admin(p)


def removido(p, nome):
    linha = p.sql("SELECT removido_em FROM jogadores WHERE codigo = ?", (p.codigos[nome],))[0]
    return linha["removido_em"] is not None


# ----- Liberar a partida -----

def test_remover_quem_travava_fecha_a_votacao(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 1)
    p.votar("Beto", 1)
    assert p.fase() == ("votacao", 1)              # Caio online e parado
    token = login_admin(p)
    remover(p, "Caio", token)
    assert p.fase() == ("resultado", 1)            # liberou na hora, sem esperar polling
    assert p.item(1)["faixa_indice"] == 1


def test_remover_quem_travava_avanca_o_resultado(partida):
    p = partida(rodadas=2)
    p.entrar("Ana", "Beto", "Caio")
    for nome in ("Ana", "Beto", "Caio"):
        p.votar(nome, 2)
    p.continuar("Ana")
    p.continuar("Beto")
    assert p.fase() == ("resultado", 1)            # Caio online e não continuou
    token = login_admin(p)
    remover(p, "Caio", token)
    assert p.fase() == ("votacao", 2)


def test_regra_todos_votaram_ignora_o_removido(partida):
    # Ninguém online: só a regra (a) poderia fechar, e ela esperava o Caio.
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 0)
    p.votar("Beto", 0)
    p.deixar_offline("Ana", "Beto", "Caio")
    token = login_admin(p)
    p.cliente.get(f"/admin/api/estado/{p.id}")
    assert p.fase() == ("votacao", 1)
    remover(p, "Caio", token)
    assert p.fase() == ("resultado", 1)


# ----- Votos do removido -----

def test_voto_do_removido_sai_da_rodada_em_andamento(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 4)
    p.votar("Beto", 0)                             # com o Beto, 0 teria 2 votos e ganharia
    token = login_admin(p)
    remover(p, "Beto", token)
    p.votar("Caio", 0)
    assert p.fase() == ("resultado", 1)
    assert p.item(1)["faixa_indice"] == 4          # sem o Beto: 1 x 1, empate -> pior (D)
    dados = p.estado("Ana").get_json()
    assert dados["distribuicao"] == [1, 0, 0, 0, 1]  # a contagem bate com a faixa


def test_rodada_ja_fechada_fica_como_esta(partida):
    # Decisão do dono: remover depois que a rodada fechou não recalcula nada.
    p = partida(rodadas=2)
    p.entrar("Ana", "Beto", "Caio")
    p.votar("Ana", 3)
    p.votar("Beto", 0)
    p.votar("Caio", 0)
    assert p.item(1)["faixa_indice"] == 0
    token = login_admin(p)
    remover(p, "Beto", token)
    assert p.item(1)["faixa_indice"] == 0
    assert p.estado("Ana").get_json()["distribuicao"] == [2, 0, 0, 1, 0]


def test_removido_sai_das_contas_de_presenca(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    token = login_admin(p)
    remover(p, "Caio", token)
    p.votar("Ana", 0)
    assert p.estado("Ana").get_json()["presenca"] == {"online": 2, "offline": 0, "faltam": 1}


def test_admin_ve_o_removido_marcado(partida):
    p = partida()
    p.entrar("Ana", "Beto", "Caio")
    token = login_admin(p)
    versao = p.cliente.get(f"/admin/api/estado/{p.id}").get_json()["versao"]
    remover(p, "Beto", token)
    dados = p.cliente.get(f"/admin/api/estado/{p.id}").get_json()
    assert dados["versao"] != versao               # as telas percebem a mudança
    marcados = {j["nome"]: (j["removido"], j["online"]) for j in dados["jogadores"]}
    assert marcados == {"Ana": (False, True), "Beto": (True, False), "Caio": (False, True)}


# ----- Link do removido -----

def test_link_do_removido_mostra_aviso_e_nao_aceita_nada(partida):
    p = partida(rodadas=2)
    p.entrar("Ana", "Beto", "Caio")
    token = login_admin(p)
    remover(p, "Beto", token)
    codigo = p.codigos["Beto"]
    pagina = p.cliente.get(f"/j/{codigo}")
    assert pagina.status_code == 403
    assert "Você foi removido desta partida" in pagina.get_data(as_text=True)
    visto_antes = p.sql("SELECT visto_em FROM jogadores WHERE codigo = ?", (codigo,))[0]["visto_em"]

    resposta = p.estado("Beto")
    assert resposta.status_code == 403 and resposta.get_json()["removido"] is True
    p.votar("Beto", 0, revisao=0, esperado=403)
    p.pular("Beto", revisao=0, esperado=403)
    p.continuar("Beto", esperado=403)
    assert p.voto_no_banco("Beto") is None
    visto_depois = p.sql("SELECT visto_em FROM jogadores WHERE codigo = ?", (codigo,))[0]["visto_em"]
    assert visto_depois == visto_antes             # nem o polling dele conta presença


# ----- Limites -----

def test_nao_remove_o_ultimo_jogador_ativo(partida):
    p = partida(jogadores=("Ana", "Beto"))
    token = login_admin(p)
    remover(p, "Ana", token)
    assert removido(p, "Ana")
    pagina = remover(p, "Beto", token)
    assert "último jogador ativo" in pagina
    assert not removido(p, "Beto")


def test_remover_de_novo_nao_faz_nada(partida):
    p = partida()
    token = login_admin(p)
    remover(p, "Ana", token)
    pagina = remover(p, "Ana", token)
    assert "já tinha sido removido" in pagina


def test_nao_remove_jogador_de_outra_partida(partida):
    p = partida()
    outra = partida(jogadores=("Zeca", "Yara"))
    token = login_admin(p)
    # Tenta remover o Zeca (da outra partida) pela URL desta partida.
    zeca = outra.sql("SELECT id FROM jogadores WHERE codigo = ?", (outra.codigos["Zeca"],))[0]["id"]
    p.cliente.post(f"/admin/partida/{p.id}/remover/{zeca}", data={"csrf_token": token})
    assert "não é desta partida" in mensagem_do_admin(p)
    assert not removido(outra, "Zeca")


def test_remover_exige_login_e_csrf(partida):
    p = partida()
    url = f"/admin/partida/{p.id}/remover/{id_do_jogador(p, 'Ana')}"
    assert p.cliente.post(url).status_code == 400          # sem token CSRF
    login_admin(p)
    assert p.cliente.post(url, data={"csrf_token": "errado"}).status_code == 400
    assert not removido(p, "Ana")

"""Páginas das telas (o JavaScript em si foi conferido no navegador; ver o pacote da etapa 3)."""
import json
import re

from test_fluxo import login_admin


def test_pagina_do_jogador_traz_as_urls_da_api(partida):
    p = partida()
    codigo = p.codigos["Ana"]
    html = p.cliente.get(f"/j/{codigo}").get_data(as_text=True)
    urls = dict(re.findall(r'data-url-(\w+)="([^"]+)"', html))
    assert urls == {
        "estado": f"/api/estado/{codigo}",
        "votar": f"/api/votar/{codigo}",
        "pular": f"/api/pular/{codigo}",
        "continuar": f"/api/continuar/{codigo}",
    }
    assert "Olá, Ana!" in html                      # o nome vem do servidor


def test_pagina_do_admin_traz_estado_ao_vivo(partida):
    p = partida()
    login_admin(p)
    html = p.cliente.get(f"/admin/partida/{p.id}").get_data(as_text=True)
    assert f'data-url-estado="/admin/api/estado/{p.id}"' in html
    nomes = re.search(r"data-nomes-estados='([^']+)'", html).group(1)
    assert json.loads(nomes)["votacao"] == "Votação"
    # Na votação, o "Forçar avanço" aparece com a fase atual; o "Iniciar" fica escondido.
    assert re.search(r'<form[^>]*id="form-iniciar"[^>]*hidden', html, re.S)
    assert 'id="forcar-estado" value="votacao"' in html
    assert 'id="forcar-rodada" value="1"' in html


def test_cor_do_texto_das_faixas(aplicacao):
    filtro = aplicacao.jinja_env.filters["cor_do_texto"]
    assert filtro("#ffff7f") == "#000000"            # amarelo claro: texto preto
    assert filtro("#1f3a93") == "#ffffff"            # azul escuro: texto branco
    assert filtro("#000000") == "#ffffff"


# ----- Versão 2: modo individual e botão remover -----

def formulario_de_nova_partida(p, modo):
    import temas
    html = p.cliente.get("/admin/nova").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    tema = next(t for t in temas.carregar(p.app.config["TEMAS_PATH"])[0] if t["valido"])
    return {
        "csrf_token": token, "modo": modo, "tema": tema["nome"], "assinatura_tema": tema["assinatura"],
        "rodadas": "3", "faixa_rotulo": ["S", "A"], "faixa_descricao": ["", ""],
        "faixa_cor": ["#ff7f7f", "#ffbf7f"], "jogadores": "Ana\nBeto",
    }


def test_nova_partida_tem_a_escolha_do_modo(partida):
    p = partida()
    login_admin(p)
    html = p.cliente.get("/admin/nova").get_data(as_text=True)
    assert 'name="modo" value="ao_vivo" checked' in html          # ao vivo é o padrão
    assert 'name="modo" value="individual"' in html
    assert "Cada um no seu ritmo" in html


def test_criar_partida_individual_pelo_formulario(partida):
    p = partida()
    login_admin(p)
    resposta = p.cliente.post("/admin/nova", data=formulario_de_nova_partida(p, "individual"))
    assert resposta.status_code == 302
    nova = int(resposta.headers["Location"].rsplit("/", 1)[1])
    linha = p.sql("SELECT modo, estado FROM partidas WHERE id = ?", (nova,))[0]
    assert (linha["modo"], linha["estado"]) == ("individual", "aberta")
    ordens = p.sql("SELECT COUNT(*) AS n FROM ordem_jogador o JOIN jogadores j ON j.id = o.jogador_id"
                   " WHERE j.partida_id = ?", (nova,))[0]["n"]
    assert ordens == 2 * 3                                           # 2 jogadores x 3 itens


def test_modo_invalido_e_recusado(partida):
    p = partida()
    login_admin(p)
    resposta = p.cliente.post("/admin/nova", data=formulario_de_nova_partida(p, "outro"))
    assert resposta.status_code == 200
    assert "Escolha um modo válido." in resposta.get_data(as_text=True)


def test_pagina_do_jogador_individual_carrega_o_script_certo(partida):
    p = partida(modo="individual", rodadas=2)
    codigo = p.codigos["Ana"]
    html = p.cliente.get(f"/j/{codigo}").get_data(as_text=True)
    urls = dict(re.findall(r'data-url-(\w+)="([^"]+)"', html))
    assert urls == {
        "estado": f"/api/estado/{codigo}",
        "responder": f"/api/responder/{codigo}",
        "finalizar": f"/api/finalizar/{codigo}",
    }
    assert "jogador_individual.js" in html and "jogador.js" not in html.replace("jogador_individual.js", "")


def test_tela_do_admin_individual(partida):
    p = partida(modo="individual", rodadas=2)
    login_admin(p)
    p.cliente.application.config["BASE_URL"] = "http://teste"      # não consulta o túnel
    try:
        html = p.cliente.get(f"/admin/partida/{p.id}").get_data(as_text=True)
    finally:
        p.cliente.application.config["BASE_URL"] = ""
    assert 'id="form-encerrar"' in html and "Encerrar e revelar" in html
    assert 'id="form-iniciar"' not in html and 'id="form-forcar"' not in html
    assert "admin_individual.js" in html and "admin_partida.js" not in html
    assert f'data-url-remover="/admin/partida/{p.id}/remover/0"' in html


def test_confirmacao_de_encerrar_ja_vem_certa_na_pagina(partida):
    # Sem esperar o polling: quem clicar antes da primeira atualização já vê o
    # aviso de resultado vazio quando ninguém finalizou.
    p = partida(modo="individual", rodadas=2)
    login_admin(p)
    p.cliente.application.config["BASE_URL"] = "http://teste"      # não consulta o túnel

    def confirmacao():
        html = p.cliente.get(f"/admin/partida/{p.id}").get_data(as_text=True)
        return re.search(r'id="form-encerrar"[^>]*data-confirmacao="([^"]+)"', html, re.S).group(1)

    try:
        assert confirmacao().startswith("Ninguém finalizou ainda")
        p.responder_tudo("Ana", lambda item_id: 0)
        p.finalizar("Ana")
        assert confirmacao().startswith("Encerrar a partida e revelar")
        p.sql("UPDATE jogadores SET removido_em = 1 WHERE codigo = ?", (p.codigos["Ana"],))    # removida não conta
        assert confirmacao().startswith("Ninguém finalizou ainda")
    finally:
        p.cliente.application.config["BASE_URL"] = ""


def test_tela_do_admin_ao_vivo_tem_remover(partida):
    p = partida()
    login_admin(p)
    p.cliente.application.config["BASE_URL"] = "http://teste"
    try:
        html = p.cliente.get(f"/admin/partida/{p.id}").get_data(as_text=True)
    finally:
        p.cliente.application.config["BASE_URL"] = ""
    assert f'data-url-remover="/admin/partida/{p.id}/remover/0"' in html
    assert 'data-csrf="' in html
    assert "admin_partida.js" in html and "admin_individual.js" not in html


def test_lista_de_partidas_mostra_o_modo(partida):
    p = partida()
    partida(modo="individual", rodadas=3)
    login_admin(p)
    html = p.cliente.get("/admin/").get_data(as_text=True)
    assert "Ao vivo" in html and "Cada um no seu ritmo" in html and "3 itens" in html

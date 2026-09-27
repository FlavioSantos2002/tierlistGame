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

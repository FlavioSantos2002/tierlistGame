"""Testes do JavaScript da tela do jogador, num navegador de verdade sem janela.

Cada cenário de tests/js/cenarios_jogador.js abre tests/js/jogador.html#<cenário>,
com um servidor falso no lugar do fetch (tests/js/servidor_falso.js).
O navegador usa "tempo virtual", então esperas de vários segundos rodam na hora.

Precisa do Edge ou do Chrome instalado (ou do caminho em NAVEGADOR_TESTES).
Sem navegador, estes testes são pulados.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PASTA_JS = Path(__file__).parent / "js"

CANDIDATOS = [
    os.environ.get("NAVEGADOR_TESTES", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]
NAVEGADOR = next((c for c in CANDIDATOS if c and os.path.exists(c)), None)

pytestmark = pytest.mark.skipif(NAVEGADOR is None, reason="Edge/Chrome não encontrado")

CENARIOS = [
    "ordem_do_voto_com_polling",
    "apagada_durante_o_post",
    "apagada_com_acao_na_fila",
    "tempo_esgotado_no_polling",
    "tempo_esgotado_na_acao",
    "resposta_atrasada_descartada",
    "revisao_enviada_e_recusa_409",
    "item_sem_votos",
]


def rodar(cenario, pasta_perfil):
    """Abre a página do cenário e devolve o texto de <pre id="resultado">."""
    url = (PASTA_JS / "jogador.html").as_uri() + "#" + cenario
    processo = subprocess.run(
        [
            NAVEGADOR, "--headless=new", "--disable-gpu", "--no-first-run",
            f"--user-data-dir={pasta_perfil}",
            "--virtual-time-budget=60000",
            "--dump-dom", url,
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    achado = re.search(r'<pre id="resultado">(.*?)</pre>', processo.stdout, re.S)
    return achado.group(1) if achado else "sem resultado: " + processo.stderr[-500:]


def test_lista_de_cenarios_confere(tmp_path):
    # Garante que nenhum cenário do arquivo JS ficou sem rodar aqui.
    assert rodar("listar", tmp_path).split(",") == CENARIOS


@pytest.mark.parametrize("cenario", CENARIOS)
def test_cenario_da_tela_do_jogador(cenario, tmp_path):
    assert rodar(cenario, tmp_path) == "OK"

"""Testes do JavaScript das telas, num navegador de verdade sem janela.

Cada página de teste em tests/js/ (jogador.html, individual.html, admin_*.html)
tem os seus cenários; cada cenário abre tests/js/<página>#<cenário>, com um
servidor falso no lugar do fetch (tests/js/servidor_falso.js).
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

# Página de teste -> cenários que ela tem (na ordem do arquivo de cenários).
PAGINAS = {
    "jogador.html": [
        "ordem_do_voto_com_polling",
        "apagada_durante_o_post",
        "apagada_com_acao_na_fila",
        "tempo_esgotado_no_polling",
        "tempo_esgotado_na_acao",
        "resposta_atrasada_descartada",
        "revisao_enviada_e_recusa_409",
        "item_sem_votos",
    ],
    "individual.html": [
        "comeca_no_primeiro_sem_resposta",
        "responder_envia_revisao_e_avanca",
        "pular_envia_null",
        "resposta_recusada_nao_avanca",
        "voltar_mostra_a_resposta_anterior",
        "tocar_na_lista_para_trocar",
        "ultimo_item_vai_para_a_revisao_e_finaliza_com_confirmacao",
        "lista_nao_navega_durante_o_envio",
        "polling_nao_perde_a_posicao",
        "polling_a_cada_5_segundos",
        "resultado_mostra_tudo",
        "compatibilidade_sem_item_em_comum_mostra_traco",
        "encerrada_sem_ter_finalizado",
        "removido_para_de_vez",
    ],
    "admin_ao_vivo.html": [
        "remover_aparece_so_nos_ativos_com_a_url_certa",
        "remover_pede_confirmacao",
        "sem_remover_depois_que_a_partida_termina",
    ],
    "admin_individual.html": [
        "progresso_de_cada_jogador",
        "listas_de_cada_jogador_e_geral",
        "confirmacao_avisa_quando_ninguem_finalizou",
        "remover_pede_confirmacao_com_o_texto_do_modo",
        "encerrada_sem_botoes",
        "lista_aberta_continua_aberta_no_redesenho",
        "polling_a_cada_5_segundos",
    ],
}


def rodar(pagina, cenario, pasta_perfil):
    """Abre a página no cenário pedido e devolve o texto de <pre id="resultado">."""
    url = (PASTA_JS / pagina).as_uri() + "#" + cenario
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
    if achado:
        return achado.group(1)
    # Já aconteceu de o navegador sair sem erro e sem imprimir nada quando
    # chamado de dentro do Git Bash; pelo PowerShell funciona.
    return (f"sem resultado: o navegador saiu com código {processo.returncode} e "
            f"{len(processo.stdout)} bytes de saída. Se estiver no Git Bash, rode pelo "
            f"PowerShell. stderr: {processo.stderr[-500:]}")


@pytest.mark.parametrize("pagina", PAGINAS)
def test_lista_de_cenarios_confere(pagina, tmp_path):
    # Garante que nenhum cenário do arquivo JS ficou sem rodar aqui.
    assert rodar(pagina, "listar", tmp_path).split(",") == PAGINAS[pagina]


@pytest.mark.parametrize(
    "pagina, cenario",
    [(pagina, cenario) for pagina, cenarios in PAGINAS.items() for cenario in cenarios],
)
def test_cenario(pagina, cenario, tmp_path):
    assert rodar(pagina, cenario, tmp_path) == "OK"

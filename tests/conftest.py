"""Preparação comum dos testes (roda só no PC).

Rodar na pasta do projeto:  python -m pytest
"""
import os
import sys
import tempfile
import time

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

# As variáveis precisam existir antes de importar o app (ele confere ao subir).
os.environ["ADMIN_TOKEN"] = "token-de-teste"
os.environ["SECRET_KEY"] = "chave-de-teste"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "inicial.db")
os.environ["TEMAS_PATH"] = os.path.join(RAIZ, "temas.json")
os.environ["TUNEL_METRICS"] = "127.0.0.1:1"
os.environ["BASE_URL"] = ""

import app as modulo_app  # noqa: E402
import banco  # noqa: E402
import jogo  # noqa: E402
from rotas_admin import criar_partida  # noqa: E402


@pytest.fixture
def aplicacao(tmp_path):
    """App com um banco novo e vazio para cada teste."""
    caminho = str(tmp_path / "teste.db")
    modulo_app.app.config.update(DB_PATH=caminho, TESTING=True)
    banco.criar_tabelas(caminho)
    return modulo_app.app


@pytest.fixture
def partida(aplicacao):
    """Fábrica de partidas de teste. Uso: p = partida(jogadores=[...], rodadas=2)."""
    def fabricar(jogadores=("Ana", "Beto", "Caio"), rodadas=2, faixas=5, iniciar=True):
        return PartidaDeTeste(aplicacao, jogadores, rodadas, faixas, iniciar)
    return fabricar


class PartidaDeTeste:
    """Atalhos para montar cenários: cria a partida e fala com a API como os jogadores."""

    def __init__(self, aplicacao, jogadores, rodadas, n_faixas, iniciar):
        self.app = aplicacao
        self.cliente = aplicacao.test_client()
        tema = {
            "nome": "Tema de teste",
            "itens": [{"nome": f"Item {n}", "imagem": f"https://x/{n}.png"} for n in range(rodadas)],
        }
        faixas = [{"rotulo": str(i), "descricao": "", "cor": "#ffffff"} for i in range(n_faixas)]
        with aplicacao.app_context():
            self.id = criar_partida(tema, rodadas, faixas, list(jogadores))
            con = banco.obter()
            self.codigos = {
                linha["nome"]: linha["codigo"]
                for linha in con.execute(
                    "SELECT nome, codigo FROM jogadores WHERE partida_id = ?", (self.id,)
                )
            }
            if iniciar:
                with banco.transacao(con):
                    jogo.iniciar(con, self.id)

    # --- chamadas à API, como o celular do jogador faria ---

    def estado(self, nome):
        return self.cliente.get(f"/api/estado/{self.codigos[nome]}")

    def acao(self, tipo, nome, **corpo):
        return self.cliente.post(f"/api/{tipo}/{self.codigos[nome]}", json=corpo)

    # Os atalhos conferem o status HTTP (200 por padrão). Assim um cenário mal
    # montado, em que a ação é recusada, falha na hora em vez de passar calado.

    # `revisao`: por padrão, a revisão atual do voto (como a tela mandaria).
    # Passar um número de propósito simula um envio antigo chegando atrasado.

    def votar(self, nome, faixa, rodada=None, esperado=200, revisao=None):
        if revisao is None:
            revisao = self.revisao(nome)
        resposta = self.acao("votar", nome, rodada=rodada or self.rodada(), faixa=faixa,
                             revisao=revisao)
        assert resposta.status_code == esperado, resposta.get_json()
        return resposta

    def pular(self, nome, rodada=None, esperado=200, revisao=None):
        if revisao is None:
            revisao = self.revisao(nome)
        resposta = self.acao("pular", nome, rodada=rodada or self.rodada(), revisao=revisao)
        assert resposta.status_code == esperado, resposta.get_json()
        return resposta

    def continuar(self, nome, rodada=None, esperado=200):
        resposta = self.acao("continuar", nome, rodada=rodada or self.rodada())
        assert resposta.status_code == esperado, resposta.get_json()
        return resposta

    # --- leitura e manipulação direta do banco ---

    def sql(self, comando, parametros=()):
        with self.app.app_context():
            con = banco.obter()
            with banco.transacao(con):
                return con.execute(comando, parametros).fetchall()

    def fase(self):
        linha = self.sql("SELECT estado, rodada_atual FROM partidas WHERE id = ?", (self.id,))[0]
        return linha["estado"], linha["rodada_atual"]

    def rodada(self):
        return self.fase()[1]

    def voto_no_banco(self, nome):
        """(faixa_indice, revisao) do jogador na rodada atual, ou None se não há linha."""
        linhas = self.sql(
            "SELECT v.faixa_indice, v.revisao FROM votos v"
            " JOIN itens i ON i.id = v.item_id JOIN jogadores j ON j.id = v.jogador_id"
            " WHERE i.partida_id = ? AND i.rodada = ? AND j.codigo = ?",
            (self.id, self.rodada(), self.codigos[nome]),
        )
        return (linhas[0]["faixa_indice"], linhas[0]["revisao"]) if linhas else None

    def revisao(self, nome):
        """Revisão atual do voto/abstenção do jogador nesta rodada (0 = nada ainda)."""
        voto = self.voto_no_banco(nome)
        return voto[1] if voto else 0

    def item(self, rodada):
        return self.sql(
            "SELECT situacao, faixa_indice FROM itens WHERE partida_id = ? AND rodada = ?",
            (self.id, rodada),
        )[0]

    def deixar_offline(self, *nomes):
        """Finge que o jogador sumiu há 100 segundos."""
        for nome in nomes:
            self.sql(
                "UPDATE jogadores SET visto_em = ? WHERE codigo = ?",
                (time.time() - 100, self.codigos[nome]),
            )

    def entrar(self, *nomes):
        """Os jogadores abrem a tela (um polling cada)."""
        for nome in nomes:
            assert self.estado(nome).status_code == 200

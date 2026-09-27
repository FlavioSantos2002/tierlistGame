"""Acesso ao banco SQLite.

- Uma conexão por requisição, guardada em `g.db` e fechada no fim da requisição.
- Modo WAL (leituras não bloqueiam a escrita) e busy_timeout (espera em vez de
  dar erro quando outra thread está escrevendo).
- Toda escrita passa por `transacao()`, que usa BEGIN IMMEDIATE: a trava de
  escrita é pega logo no início, então duas threads nunca mudam a mesma
  partida ao mesmo tempo.
"""
import sqlite3
from contextlib import contextmanager

from flask import current_app, g

ESQUEMA = """
CREATE TABLE IF NOT EXISTS partidas (
    -- AUTOINCREMENT: o id de uma partida apagada nunca é reaproveitado.
    -- Sem isso, uma aba antiga com "/partida/1/apagar" poderia apagar
    -- uma partida nova que recebeu o mesmo id 1.
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_nome     TEXT    NOT NULL,
    estado        TEXT    NOT NULL DEFAULT 'espera'
                  CHECK (estado IN ('espera', 'votacao', 'resultado', 'encerrada')),
    rodada_atual  INTEGER NOT NULL DEFAULT 0,   -- 0 enquanto está em espera
    total_rodadas INTEGER NOT NULL,
    versao        INTEGER NOT NULL DEFAULT 1,   -- sobe a cada mudança
    criada_em     REAL    NOT NULL              -- horário Unix (time.time())
);

CREATE TABLE IF NOT EXISTS faixas (
    id         INTEGER PRIMARY KEY,
    partida_id INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    indice     INTEGER NOT NULL,                -- 0 = melhor faixa
    rotulo     TEXT    NOT NULL,
    descricao  TEXT    NOT NULL DEFAULT '',
    cor        TEXT    NOT NULL,
    UNIQUE (partida_id, indice)
);

CREATE TABLE IF NOT EXISTS jogadores (
    id         INTEGER PRIMARY KEY,
    partida_id INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    nome       TEXT    NOT NULL,
    codigo     TEXT    NOT NULL UNIQUE,
    visto_em   REAL,                            -- NULL = nunca entrou
    UNIQUE (partida_id, nome)
);

CREATE TABLE IF NOT EXISTS itens (
    id           INTEGER PRIMARY KEY,
    partida_id   INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    rodada       INTEGER NOT NULL,              -- rodada em que o item aparece (1..T)
    nome         TEXT    NOT NULL,
    imagem       TEXT    NOT NULL,
    situacao     TEXT    NOT NULL DEFAULT 'pendente'
                 CHECK (situacao IN ('pendente', 'classificado', 'pulado')),
    faixa_indice INTEGER,                       -- preenchido quando classificado
    UNIQUE (partida_id, rodada)
);

CREATE TABLE IF NOT EXISTS votos (
    item_id      INTEGER NOT NULL REFERENCES itens (id) ON DELETE CASCADE,
    jogador_id   INTEGER NOT NULL REFERENCES jogadores (id) ON DELETE CASCADE,
    faixa_indice INTEGER,                       -- NULL = absteve-se ("Pular")
    votado_em    REAL    NOT NULL,
    -- Quantas vezes o voto/abstenção deste jogador neste item foi aceito.
    -- O jogador manda a revisão que estava vendo; um pedido antigo (que chegou
    -- atrasado ao servidor) é recusado em vez de desfazer uma escolha mais nova.
    revisao      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id, jogador_id)
);

CREATE TABLE IF NOT EXISTS continuar (
    item_id    INTEGER NOT NULL REFERENCES itens (id) ON DELETE CASCADE,
    jogador_id INTEGER NOT NULL REFERENCES jogadores (id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, jogador_id)
);
"""


def conectar(caminho):
    """Abre uma conexão já configurada.

    isolation_level=None desliga as transações automáticas do módulo sqlite3;
    nós mesmos abrimos e fechamos as transações em `transacao()`.
    """
    con = sqlite3.connect(caminho, timeout=5, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA foreign_keys = ON")
    # Com WAL, NORMAL continua seguro contra corrupção e grava bem menos no
    # armazenamento do celular (o polling escreve o visto_em a cada 2 s).
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def criar_tabelas(caminho):
    """Cria as tabelas (se ainda não existirem) e liga o modo WAL.

    O modo WAL fica gravado no arquivo do banco, basta ligar uma vez.
    """
    con = conectar(caminho)
    try:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(ESQUEMA)
        conferir_esquema(con, caminho)
    finally:
        con.close()


def conferir_esquema(con, caminho):
    """Recusa bancos criados por uma versão antiga do esquema.

    CREATE TABLE IF NOT EXISTS não altera uma tabela que já existe. Então, se o
    arquivo do banco for de antes de alguma mudança do esquema (AUTOINCREMENT
    em partidas, coluna revisao em votos), avisamos em vez de seguir com a
    tabela antiga.
    """
    linha = con.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'partidas'"
    ).fetchone()
    colunas_votos = {c["name"] for c in con.execute("PRAGMA table_info(votos)")}
    if "AUTOINCREMENT" not in linha["sql"].upper() or "revisao" not in colunas_votos:
        raise RuntimeError(
            f"O banco {caminho} foi criado por uma versão antiga do app. "
            "Se for um banco de teste descartável: pare o app e apague o arquivo "
            "(e os -wal/-shm); ele será recriado vazio, e TODAS as partidas serão perdidas. "
            "Se os dados precisarem ser mantidos, NÃO apague: faça uma cópia de "
            "segurança do arquivo e peça uma migração."
        )


def obter():
    """Devolve a conexão da requisição atual (abre na primeira chamada)."""
    if "db" not in g:
        g.db = conectar(current_app.config["DB_PATH"])
    return g.db


def fechar(erro=None):
    """Fecha a conexão no fim da requisição (registrado no app.py)."""
    con = g.pop("db", None)
    if con is not None:
        con.close()


@contextmanager
def transacao(con):
    """Bloco de escrita: BEGIN IMMEDIATE ... COMMIT (ou ROLLBACK se der erro).

    Uso:
        with banco.transacao(con):
            con.execute("UPDATE ...")
    """
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")

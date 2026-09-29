"""Acesso ao banco SQLite.

- Uma conexão por requisição, guardada em `g.db` e fechada no fim da requisição.
- Modo WAL (leituras não bloqueiam a escrita) e busy_timeout (espera em vez de
  dar erro quando outra thread está escrevendo).
- Toda escrita passa por `transacao()`, que usa BEGIN IMMEDIATE: a trava de
  escrita é pega logo no início, então duas threads nunca mudam a mesma
  partida ao mesmo tempo.
- A versão do esquema fica em PRAGMA user_version. Ao subir, o app cria o banco
  (se não existir) ou migra um banco antigo, sem apagar nada (ver `preparar`).
"""
import os
import sqlite3
import time
from contextlib import contextmanager

from flask import current_app, g

# Versão atual do esquema. A versão 1 do app não gravava user_version (fica 0).
VERSAO_ESQUEMA = 2

# Tabela de partidas da versão 2. Fica separada porque a migração da v1 cria
# a tabela nova com este mesmo texto (com outro nome) antes de trocar.
TABELA_PARTIDAS = """
CREATE TABLE {nome} (
    -- AUTOINCREMENT: o id de uma partida apagada nunca é reaproveitado.
    -- Sem isso, uma aba antiga com "/partida/1/apagar" poderia apagar
    -- uma partida nova que recebeu o mesmo id 1.
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_nome     TEXT    NOT NULL,
    modo          TEXT    NOT NULL DEFAULT 'ao_vivo'
                  CHECK (modo IN ('ao_vivo', 'individual')),
    -- ao vivo:    espera -> (votacao <-> resultado) -> encerrada
    -- individual: aberta -> encerrada
    estado        TEXT    NOT NULL DEFAULT 'espera'
                  CHECK (estado IN ('espera', 'votacao', 'resultado', 'aberta', 'encerrada')),
    rodada_atual  INTEGER NOT NULL DEFAULT 0,   -- 0 enquanto está em espera
    total_rodadas INTEGER NOT NULL,             -- no modo individual: número de itens
    versao        INTEGER NOT NULL DEFAULT 1,   -- sobe a cada mudança
    criada_em     REAL    NOT NULL              -- horário Unix (time.time())
)
"""

# Tabela nova da versão 2 (modo individual). "IF NOT EXISTS" porque a migração
# também a cria.
TABELA_ORDEM = """
CREATE TABLE IF NOT EXISTS ordem_jogador (
    -- Modo individual: a ordem embaralhada dos itens de cada jogador,
    -- sorteada uma vez na criação da partida.
    jogador_id INTEGER NOT NULL REFERENCES jogadores (id) ON DELETE CASCADE,
    posicao    INTEGER NOT NULL,                -- 1..T
    item_id    INTEGER NOT NULL REFERENCES itens (id) ON DELETE CASCADE,
    PRIMARY KEY (jogador_id, posicao),
    UNIQUE (jogador_id, item_id)
)
"""

# Esquema completo de um banco novo.
ESQUEMA = TABELA_PARTIDAS.format(nome="partidas") + """;

CREATE TABLE faixas (
    id         INTEGER PRIMARY KEY,
    partida_id INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    indice     INTEGER NOT NULL,                -- 0 = melhor faixa
    rotulo     TEXT    NOT NULL,
    descricao  TEXT    NOT NULL DEFAULT '',
    cor        TEXT    NOT NULL,
    UNIQUE (partida_id, indice)
);

CREATE TABLE jogadores (
    id            INTEGER PRIMARY KEY,
    partida_id    INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    nome          TEXT    NOT NULL,
    codigo        TEXT    NOT NULL UNIQUE,
    visto_em      REAL,                         -- NULL = nunca entrou
    removido_em   REAL,                         -- NULL = ativo; removido é permanente
    finalizado_em REAL,                         -- modo individual: NULL = não finalizou
    UNIQUE (partida_id, nome)
);

CREATE TABLE itens (
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

CREATE TABLE votos (
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

CREATE TABLE continuar (
    item_id    INTEGER NOT NULL REFERENCES itens (id) ON DELETE CASCADE,
    jogador_id INTEGER NOT NULL REFERENCES jogadores (id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, jogador_id)
);
""" + TABELA_ORDEM + ";\n"

MENSAGEM_BANCO_MUITO_ANTIGO = (
    "O banco {caminho} foi criado por uma versão de teste antiga do app, que não tem "
    "migração automática. Se for um banco de teste descartável: pare o app e apague o "
    "arquivo (e os -wal/-shm); ele será recriado vazio, e TODAS as partidas serão perdidas. "
    "Se os dados precisarem ser mantidos, NÃO apague: faça uma cópia de segurança do "
    "arquivo e peça uma migração."
)


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


# ---------------------------------------------------------------------------
# Criação e migração (roda uma vez, quando o app sobe)
# ---------------------------------------------------------------------------

def preparar(caminho):
    """Deixa o banco no esquema atual: cria se não existir, migra se for antigo.

    Pode rodar quantas vezes for preciso: num banco já atualizado, não faz nada.
    """
    con = conectar(caminho)
    try:
        con.execute("PRAGMA journal_mode = WAL")   # fica gravado no arquivo
        versao = con.execute("PRAGMA user_version").fetchone()[0]
        if not _tabela_existe(con, "partidas"):
            _criar_do_zero(con)
        elif versao == 0:
            _conferir_versao_1(con, caminho)
            fazer_backup(caminho, "antes-v2")
            _migrar_1_para_2(con)
        elif versao > VERSAO_ESQUEMA:
            raise RuntimeError(
                f"O banco {caminho} é da versão {versao} do esquema, mais nova que este "
                f"app (versão {VERSAO_ESQUEMA}). Atualize os arquivos do app."
            )
    finally:
        con.close()


def _tabela_existe(con, nome):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nome,)
    ).fetchone() is not None


def _colunas(con, tabela):
    return {linha["name"] for linha in con.execute(f"PRAGMA table_info({tabela})")}


def _criar_do_zero(con):
    # Tudo num script só, entre BEGIN e COMMIT: ou cria o esquema inteiro
    # (já marcado com a versão atual), ou não cria nada.
    try:
        con.executescript(
            "BEGIN IMMEDIATE;\n" + ESQUEMA
            + f"PRAGMA user_version = {VERSAO_ESQUEMA};\nCOMMIT;\n"
        )
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def _conferir_versao_1(con, caminho):
    """Um banco sem user_version tem de ser da versão 1 FINAL (a do celular).

    Bancos de testes antigos (antes do AUTOINCREMENT ou da coluna revisao)
    não têm migração: continuam sendo recusados, como na versão 1.
    """
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'partidas'"
    ).fetchone()["sql"]
    if "AUTOINCREMENT" not in sql.upper() or "revisao" not in _colunas(con, "votos"):
        raise RuntimeError(MENSAGEM_BANCO_MUITO_ANTIGO.format(caminho=caminho))


def fazer_backup(caminho, sufixo):
    """Cópia completa do banco em backups/ (mesmo com o app rodando, em WAL).

    Devolve o caminho da cópia. Se algo der errado, levanta erro: quem chama
    (a migração) não continua sem o backup.
    """
    pasta = os.path.join(os.path.dirname(os.path.abspath(caminho)), "backups")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, time.strftime(f"tierlist-{sufixo}-%Y%m%d-%H%M%S.db"))
    origem = sqlite3.connect(caminho)
    copia = sqlite3.connect(destino)
    try:
        origem.backup(copia)
        resultado = copia.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        copia.close()
        origem.close()
    if resultado != "ok":
        raise RuntimeError(f"O backup {destino} saiu com problema ({resultado}). Migração cancelada.")
    return destino


def _migrar_1_para_2(con):
    """Versão 1 -> 2, numa transação só (se algo falhar, nada muda).

    - partidas: nova coluna "modo" e o estado "aberta". O SQLite não deixa mudar
      o CHECK de uma tabela existente, então a tabela é reconstruída pelo
      procedimento oficial (criar nova, copiar, apagar a velha, renomear).
    - jogadores: colunas removido_em e finalizado_em.
    - tabela nova ordem_jogador.
    Todas as partidas antigas ficam no modo "ao_vivo".
    """
    # As chaves estrangeiras precisam ficar desligadas durante a troca da tabela
    # (senão apagar a tabela velha apagaria em cascata faixas, jogadores...).
    # Esse PRAGMA só funciona fora de transação.
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            _reconstruir_partidas(con)
            colunas = _colunas(con, "jogadores")
            for coluna in ("removido_em", "finalizado_em"):
                if coluna not in colunas:
                    con.execute(f"ALTER TABLE jogadores ADD COLUMN {coluna} REAL")
            con.execute(TABELA_ORDEM)
            problemas = con.execute("PRAGMA foreign_key_check").fetchall()
            if problemas:
                raise RuntimeError(f"Migração cancelada: referências quebradas {problemas[:5]}")
            con.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        con.execute("COMMIT")
    finally:
        con.execute("PRAGMA foreign_keys = ON")


def _reconstruir_partidas(con):
    # O contador do AUTOINCREMENT precisa sobreviver à troca: é ele que impede
    # reaproveitar o id de uma partida já apagada.
    linha = con.execute("SELECT seq FROM sqlite_sequence WHERE name = 'partidas'").fetchone()
    contador = linha["seq"] if linha else 0

    con.execute(TABELA_PARTIDAS.format(nome="partidas_v2"))
    con.execute(
        "INSERT INTO partidas_v2"
        " (id, tema_nome, modo, estado, rodada_atual, total_rodadas, versao, criada_em)"
        " SELECT id, tema_nome, 'ao_vivo', estado, rodada_atual, total_rodadas, versao, criada_em"
        " FROM partidas"
    )
    con.execute("DROP TABLE partidas")
    con.execute("ALTER TABLE partidas_v2 RENAME TO partidas")

    con.execute("DELETE FROM sqlite_sequence WHERE name IN ('partidas', 'partidas_v2')")
    maior_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM partidas").fetchone()[0]
    con.execute(
        "INSERT INTO sqlite_sequence (name, seq) VALUES ('partidas', ?)",
        (max(contador, maior_id),),
    )


# ---------------------------------------------------------------------------
# Uso normal
# ---------------------------------------------------------------------------

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

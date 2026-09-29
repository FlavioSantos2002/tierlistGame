"""Migração do banco da versão 1 (o tierlist.db que já está no celular) para a 2."""
import glob
import os
import sqlite3
from pathlib import Path

import pytest

import banco

ESQUEMA_V1 = (Path(__file__).parent / "esquema_v1.sql").read_text(encoding="utf-8")


def montar_banco_v1(caminho):
    """Banco com o esquema exato da v1 e dados parecidos com os de uma partida real."""
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA_V1)
    for pid, estado, rodada in ((1, "encerrada", 2), (2, "votacao", 1), (3, "espera", 0)):
        con.execute(
            "INSERT INTO partidas (id, tema_nome, estado, rodada_atual, total_rodadas, versao, criada_em)"
            " VALUES (?, 'Pokémon', ?, ?, 2, 7, 1000)",
            (pid, estado, rodada),
        )
        for indice, rotulo in enumerate("SABCD"):
            con.execute(
                "INSERT INTO faixas (partida_id, indice, rotulo, cor) VALUES (?, ?, ?, '#ffffff')",
                (pid, indice, rotulo),
            )
        for nome in ("Ana", "Beto"):
            con.execute(
                "INSERT INTO jogadores (partida_id, nome, codigo, visto_em) VALUES (?, ?, ?, 999)",
                (pid, nome, f"{nome}-{pid}"),
            )
        for n in (1, 2):
            con.execute(
                "INSERT INTO itens (partida_id, rodada, nome, imagem) VALUES (?, ?, ?, 'https://x')",
                (pid, n, f"Item {n}"),
            )
    # Votos e "continuar" na partida 1.
    item = con.execute("SELECT id FROM itens WHERE partida_id = 1 AND rodada = 1").fetchone()[0]
    for jogador, faixa in con.execute("SELECT id, id % 2 FROM jogadores WHERE partida_id = 1").fetchall():
        con.execute(
            "INSERT INTO votos (item_id, jogador_id, faixa_indice, votado_em, revisao) VALUES (?, ?, ?, 1, 1)",
            (item, jogador, faixa),
        )
        con.execute("INSERT INTO continuar (item_id, jogador_id) VALUES (?, ?)", (item, jogador))
    con.execute("UPDATE itens SET situacao = 'classificado', faixa_indice = 1 WHERE id = ?", (item,))
    con.commit()
    # A partida 3 foi apagada: o contador do AUTOINCREMENT fica em 3, o maior id em 2.
    con.execute("DELETE FROM partidas WHERE id = 3")
    con.commit()
    con.close()


def contar(caminho):
    con = sqlite3.connect(caminho)
    tabelas = ("partidas", "faixas", "jogadores", "itens", "votos", "continuar")
    resultado = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tabelas}
    con.close()
    return resultado


def ler(caminho, sql, parametros=()):
    con = sqlite3.connect(caminho)
    try:
        return con.execute(sql, parametros).fetchall()
    finally:
        con.close()


def colunas(caminho, tabela):
    return {linha[1] for linha in ler(caminho, f"PRAGMA table_info({tabela})")}


@pytest.fixture
def banco_v1(tmp_path):
    caminho = str(tmp_path / "tierlist.db")
    montar_banco_v1(caminho)
    return caminho


# ----- Migração -----

def test_migra_sem_perder_dados(banco_v1):
    antes = contar(banco_v1)
    partidas_antes = ler(banco_v1, "SELECT id, tema_nome, estado, rodada_atual, versao FROM partidas ORDER BY id")
    assert ler(banco_v1, "PRAGMA user_version")[0][0] == 0

    banco.preparar(banco_v1)

    assert ler(banco_v1, "PRAGMA user_version")[0][0] == 2
    assert contar(banco_v1) == antes
    assert ler(banco_v1, "SELECT id, tema_nome, estado, rodada_atual, versao FROM partidas ORDER BY id") \
        == partidas_antes
    assert ler(banco_v1, "SELECT DISTINCT modo FROM partidas") == [("ao_vivo",)]
    assert {"removido_em", "finalizado_em"} <= colunas(banco_v1, "jogadores")
    assert ler(banco_v1, "SELECT COUNT(*) FROM jogadores WHERE removido_em IS NOT NULL")[0][0] == 0
    assert "ordem_jogador" in {n for (n,) in ler(banco_v1, "SELECT name FROM sqlite_master")}
    assert ler(banco_v1, "PRAGMA foreign_key_check") == []
    assert ler(banco_v1, "PRAGMA integrity_check") == [("ok",)]


def test_contador_de_ids_sobrevive(banco_v1):
    # A partida 3 tinha sido apagada: a próxima tem de ser a 4, nunca a 3 de novo.
    banco.preparar(banco_v1)
    con = banco.conectar(banco_v1)
    cursor = con.execute(
        "INSERT INTO partidas (tema_nome, total_rodadas, criada_em) VALUES ('Novo', 2, 1)"
    )
    assert cursor.lastrowid == 4
    con.close()


def test_apagar_em_cascata_continua_funcionando(banco_v1):
    banco.preparar(banco_v1)
    con = banco.conectar(banco_v1)                 # conexão do app: chaves estrangeiras ligadas
    con.execute("DELETE FROM partidas WHERE id = 1")
    con.close()
    for tabela in ("faixas", "jogadores", "itens"):
        assert ler(banco_v1, f"SELECT COUNT(*) FROM {tabela} WHERE partida_id = 1")[0][0] == 0
    assert ler(banco_v1, "SELECT COUNT(*) FROM votos")[0][0] == 0
    assert ler(banco_v1, "SELECT COUNT(*) FROM continuar")[0][0] == 0
    assert ler(banco_v1, "SELECT COUNT(*) FROM jogadores WHERE partida_id = 2")[0][0] == 2


def test_migracao_pode_rodar_varias_vezes(banco_v1):
    banco.preparar(banco_v1)
    depois_da_primeira = contar(banco_v1)
    banco.preparar(banco_v1)
    banco.preparar(banco_v1)
    assert contar(banco_v1) == depois_da_primeira
    assert ler(banco_v1, "PRAGMA user_version")[0][0] == 2
    # Só um backup: as rodadas seguintes não tinham nada a migrar.
    assert len(glob.glob(os.path.join(os.path.dirname(banco_v1), "backups", "*.db"))) == 1


def test_backup_antes_de_migrar(banco_v1):
    antes = contar(banco_v1)
    banco.preparar(banco_v1)
    copias = glob.glob(os.path.join(os.path.dirname(banco_v1), "backups", "tierlist-antes-v2-*.db"))
    assert len(copias) == 1
    assert ler(copias[0], "PRAGMA user_version")[0][0] == 0      # a cópia é do banco da v1
    assert contar(copias[0]) == antes
    assert "modo" not in colunas(copias[0], "partidas")


def test_falha_no_meio_nao_muda_nada(banco_v1, monkeypatch):
    antes = contar(banco_v1)
    # Faz o último passo da migração falhar (depois de reconstruir partidas e
    # adicionar as colunas): tudo tem de voltar ao que era.
    monkeypatch.setattr(banco, "TABELA_ORDEM", "CREATE TABLE comando invalido (")
    with pytest.raises(sqlite3.OperationalError):
        banco.preparar(banco_v1)
    assert ler(banco_v1, "PRAGMA user_version")[0][0] == 0
    assert "modo" not in colunas(banco_v1, "partidas")
    assert "removido_em" not in colunas(banco_v1, "jogadores")
    assert contar(banco_v1) == antes
    assert ler(banco_v1, "PRAGMA foreign_key_check") == []
    # Com o problema resolvido, a migração passa.
    monkeypatch.undo()
    banco.preparar(banco_v1)
    assert ler(banco_v1, "PRAGMA user_version")[0][0] == 2
    assert contar(banco_v1) == antes


def test_estados_e_modos_novos_aceitos(banco_v1):
    banco.preparar(banco_v1)
    con = banco.conectar(banco_v1)
    con.execute(
        "INSERT INTO partidas (tema_nome, modo, estado, total_rodadas, criada_em)"
        " VALUES ('X', 'individual', 'aberta', 2, 1)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO partidas (tema_nome, modo, total_rodadas, criada_em) VALUES ('X', 'outro', 2, 1)"
        )
    con.close()


# ----- Outros casos -----

def test_banco_novo_nasce_na_versao_2(tmp_path):
    caminho = str(tmp_path / "novo.db")
    banco.preparar(caminho)
    assert ler(caminho, "PRAGMA user_version")[0][0] == 2
    assert {"modo"} <= colunas(caminho, "partidas")
    assert {"removido_em", "finalizado_em"} <= colunas(caminho, "jogadores")
    assert not os.path.exists(tmp_path / "backups")          # nada a migrar, nada a copiar
    banco.preparar(caminho)                                   # de novo: sem erro


def test_banco_de_teste_antigo_da_v1_continua_recusado(tmp_path):
    caminho = str(tmp_path / "velho.db")
    con = sqlite3.connect(caminho)
    con.executescript(ESQUEMA_V1.replace("    revisao      INTEGER NOT NULL DEFAULT 1,\n", ""))
    con.close()
    with pytest.raises(RuntimeError, match="versão de teste antiga"):
        banco.preparar(caminho)


def test_banco_de_versao_mais_nova_e_recusado(tmp_path):
    caminho = str(tmp_path / "futuro.db")
    banco.preparar(caminho)
    ler(caminho, "PRAGMA user_version = 3")
    with pytest.raises(RuntimeError, match="mais nova"):
        banco.preparar(caminho)


def test_partida_da_v1_continua_jogavel_depois_de_migrar(banco_v1, aplicacao):
    # A partida 2 estava em votação na v1: depois da migração, o jogador
    # abre o link e vota normalmente.
    banco.preparar(banco_v1)
    aplicacao.config["DB_PATH"] = banco_v1
    cliente = aplicacao.test_client()
    estado = cliente.get("/api/estado/Ana-2").get_json()
    assert estado["estado"] == "votacao" and estado["rodada"] == 1
    resposta = cliente.post("/api/votar/Ana-2", json={"rodada": 1, "faixa": 0, "revisao": 0})
    assert resposta.status_code == 200
    assert resposta.get_json()["eu"]["voto"] == 0

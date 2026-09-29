"""Confere a migração v1 -> v2 num BACKUP do banco real (roda só no PC).

Uso (PowerShell, na pasta do projeto):
    .\\.venv\\Scripts\\python ferramentas\\conferir_migracao.py teste-migracao\\tierlist-AAAAMMDD-HHMMSS.db

O arquivo informado NÃO é alterado: o script copia para "<nome>-migrado.db" e
migra a cópia. Depois compara, linha por linha, todos os dados da v1 antes e
depois, confere o esquema novo e roda a migração de novo (tem de não mudar nada).
"""
import glob
import os
import shutil
import sqlite3
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import banco  # noqa: E402

# Colunas que existiam na v1, por tabela (ordenadas pela chave).
COLUNAS_V1 = {
    "partidas": ("id, tema_nome, estado, rodada_atual, total_rodadas, versao, criada_em", "id"),
    "faixas": ("id, partida_id, indice, rotulo, descricao, cor", "id"),
    "jogadores": ("id, partida_id, nome, codigo, visto_em", "id"),
    "itens": ("id, partida_id, rodada, nome, imagem, situacao, faixa_indice", "id"),
    "votos": ("item_id, jogador_id, faixa_indice, votado_em, revisao", "item_id, jogador_id"),
    "continuar": ("item_id, jogador_id", "item_id, jogador_id"),
}

problemas = []


def conferir(condicao, mensagem):
    print(("  ok     " if condicao else "  FALHOU ") + mensagem)
    if not condicao:
        problemas.append(mensagem)


def retrato(caminho):
    """Todos os dados da v1 (e o contador de ids) de um banco."""
    con = sqlite3.connect(caminho)
    try:
        dados = {
            tabela: con.execute(f"SELECT {colunas} FROM {tabela} ORDER BY {chave}").fetchall()
            for tabela, (colunas, chave) in COLUNAS_V1.items()
        }
        linha = con.execute("SELECT seq FROM sqlite_sequence WHERE name = 'partidas'").fetchone()
        dados["contador_de_ids"] = linha[0] if linha else 0
        return dados
    finally:
        con.close()


def consultar(caminho, sql):
    con = sqlite3.connect(caminho)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def main(original):
    copia = os.path.splitext(original)[0] + "-migrado.db"
    for resto in (copia, copia + "-wal", copia + "-shm"):
        if os.path.exists(resto):
            os.remove(resto)
    shutil.copyfile(original, copia)
    pasta_backups = os.path.join(os.path.dirname(os.path.abspath(copia)), "backups")
    backups_antes = set(glob.glob(os.path.join(pasta_backups, "*.db")))

    print(f"Banco: {original}")
    print("1) Antes da migração")
    conferir(consultar(copia, "PRAGMA integrity_check") == [("ok",)], "integridade do backup")
    conferir(consultar(copia, "PRAGMA user_version") == [(0,)], "é um banco da v1 (user_version 0)")
    antes = retrato(copia)
    for tabela in COLUNAS_V1:
        print(f"         {tabela}: {len(antes[tabela])} linhas")

    print("2) Primeira migração")
    banco.preparar(copia)
    depois = retrato(copia)
    conferir(consultar(copia, "PRAGMA user_version") == [(2,)], "agora está na versão 2")
    for tabela in COLUNAS_V1:
        conferir(depois[tabela] == antes[tabela], f"{tabela}: todos os dados iguais aos da v1")
    conferir(depois["contador_de_ids"] >= antes["contador_de_ids"],
             f"contador de ids preservado ({antes['contador_de_ids']} -> {depois['contador_de_ids']})")
    conferir(consultar(copia, "SELECT COUNT(*) FROM partidas WHERE modo != 'ao_vivo'") == [(0,)],
             "todas as partidas antigas ficaram no modo ao vivo")
    conferir(consultar(copia, "SELECT COUNT(*) FROM jogadores"
                              " WHERE removido_em IS NOT NULL OR finalizado_em IS NOT NULL") == [(0,)],
             "nenhum jogador marcado como removido ou finalizado")
    conferir(consultar(copia, "PRAGMA integrity_check") == [("ok",)], "integridade depois de migrar")
    conferir(consultar(copia, "PRAGMA foreign_key_check") == [], "nenhuma referência quebrada")
    novos = set(glob.glob(os.path.join(pasta_backups, "*.db"))) - backups_antes
    conferir(len(novos) == 1, "a migração fez 1 backup antes de mudar o banco")

    print("3) Segunda migração (não pode mudar nada)")
    banco.preparar(copia)
    conferir(retrato(copia) == depois, "dados idênticos aos da primeira migração")
    conferir(set(glob.glob(os.path.join(pasta_backups, "*.db"))) - backups_antes == novos,
             "nenhum backup novo (não havia nada a migrar)")

    print()
    if problemas:
        print(f"RESULTADO: {len(problemas)} problema(s). NÃO atualize o celular; mande esta saída.")
        return 1
    print("RESULTADO: tudo certo. A migração preserva os dados deste banco.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isfile(sys.argv[1]):
        sys.exit("Uso: python ferramentas/conferir_migracao.py <backup-do-celular.db>")
    sys.exit(main(sys.argv[1]))

"""Modo individual ("cada um no seu ritmo"): regras e mudanças de estado.

Partida:  aberta -> encerrada
          (encerra sozinha quando todos os jogadores ativos finalizaram,
           ou quando o admin clica em "Encerrar e revelar")
Jogador:  preenchendo -> finalizado (respostas travadas); removido a qualquer hora.

- Os itens são os mesmos para todos; a ORDEM é sorteada para cada jogador na
  criação (tabela ordem_jogador) e nunca muda.
- Cada resposta (faixa ou "pulei") vai para a tabela `votos`, a mesma do modo
  ao vivo, com a mesma revisão contra envios atrasados.
- Não há presença online: nada aqui depende de quem está com a página aberta.
- A tier list geral NÃO é gravada: é calculada na hora, pela regra da maioria,
  só com as respostas de quem já finalizou (e não foi removido).

Como em jogo.py, as funções que gravam devem rodar dentro de banco.transacao.
"""
import hashlib
import json
import random
from fractions import Fraction

from jogo import AcaoInvalida, calcular_faixa, subir_versao, versao_do_estado


# ===========================================================================
# 1. Regras puras
# ===========================================================================

def compatibilidade(minhas, geral, numero_de_faixas):
    """Compatibilidade (0 a 100) entre as respostas de um jogador e a geral.

    `minhas` e `geral`: {item_id: índice da faixa, ou None se pulado}.
    Só entram os itens que os DOIS classificaram. Para cada um:
        nota = 1 - |faixa minha - faixa geral| / (número de faixas - 1)
    O resultado é a média das notas, em porcentagem, arredondada para o
    inteiro mais próximo (meio ponto arredonda para cima). Sem nenhum item
    em comum, devolve None (a tela mostra "—").

    A conta é feita com frações exatas, sem erro de ponto flutuante.
    """
    distancia_maxima = numero_de_faixas - 1
    notas = [
        1 - Fraction(abs(minhas[item] - geral[item]), distancia_maxima)
        for item in minhas
        if minhas[item] is not None and geral.get(item) is not None
    ]
    if not notas:
        return None
    porcentagem = sum(notas) / len(notas) * 100
    return int(porcentagem + Fraction(1, 2))       # arredonda (x,5 sobe)


def tier_geral(respostas_de_quem_finalizou, ids_dos_itens):
    """Faixa de cada item pela regra da maioria. Pulos não contam.

    `respostas_de_quem_finalizou`: {jogador_id: {item_id: faixa ou None}}.
    Devolve {item_id: faixa, ou None se ninguém classificou o item}.
    """
    geral = {}
    for item in ids_dos_itens:
        votos = [
            respostas[item]
            for respostas in respostas_de_quem_finalizou.values()
            if respostas.get(item) is not None
        ]
        geral[item] = calcular_faixa(votos)
    return geral


# ===========================================================================
# 2. Criação: ordem de cada jogador
# ===========================================================================

def sortear_ordens(con, partida_id, sorteio=random):
    """Sorteia, uma vez só, a ordem dos itens de cada jogador da partida."""
    itens = [l["id"] for l in con.execute(
        "SELECT id FROM itens WHERE partida_id = ? ORDER BY rodada", (partida_id,))]
    jogadores = [l["id"] for l in con.execute(
        "SELECT id FROM jogadores WHERE partida_id = ? ORDER BY id", (partida_id,))]
    for jogador_id in jogadores:
        ordem = sorteio.sample(itens, len(itens))
        con.executemany(
            "INSERT INTO ordem_jogador (jogador_id, posicao, item_id) VALUES (?, ?, ?)",
            [(jogador_id, posicao, item_id) for posicao, item_id in enumerate(ordem, start=1)],
        )


# ===========================================================================
# 3. Leitura da partida
# ===========================================================================

class Situacao:
    """Tudo o que as regras e as telas precisam de uma partida individual."""

    def __init__(self, con, partida_id):
        self.partida = dict(con.execute(
            "SELECT * FROM partidas WHERE id = ?", (partida_id,)).fetchone())
        self.faixas = [dict(f) for f in con.execute(
            "SELECT indice, rotulo, descricao, cor FROM faixas WHERE partida_id = ? ORDER BY indice",
            (partida_id,))]
        self.itens = {l["id"]: dict(l) for l in con.execute(
            "SELECT id, rodada, nome, imagem FROM itens WHERE partida_id = ? ORDER BY rodada",
            (partida_id,))}
        self.jogadores = [dict(j) for j in con.execute(
            "SELECT id, nome, visto_em, removido_em, finalizado_em FROM jogadores"
            " WHERE partida_id = ? ORDER BY id", (partida_id,))]
        # Respostas de todos: {jogador_id: {item_id: (faixa ou None, revisao)}}
        self.respostas = {j["id"]: {} for j in self.jogadores}
        for linha in con.execute(
            "SELECT v.jogador_id, v.item_id, v.faixa_indice, v.revisao FROM votos v"
            " JOIN itens i ON i.id = v.item_id WHERE i.partida_id = ?", (partida_id,)
        ):
            self.respostas[linha["jogador_id"]][linha["item_id"]] = (
                linha["faixa_indice"], linha["revisao"])
        self._con = con

    @property
    def estado(self):
        return self.partida["estado"]

    @property
    def ativos(self):
        return [j for j in self.jogadores if j["removido_em"] is None]

    @property
    def finalizados(self):
        """Ativos que já finalizaram: só as respostas deles entram na geral."""
        return [j for j in self.ativos if j["finalizado_em"] is not None]

    def jogador(self, jogador_id):
        return next(j for j in self.jogadores if j["id"] == jogador_id)

    def faixas_de(self, jogador_id):
        """{item_id: faixa ou None} das respostas de um jogador."""
        return {item: faixa for item, (faixa, _) in self.respostas[jogador_id].items()}

    def ordem_de(self, jogador_id):
        return [l["item_id"] for l in self._con.execute(
            "SELECT item_id FROM ordem_jogador WHERE jogador_id = ? ORDER BY posicao",
            (jogador_id,))]

    def geral(self):
        """Tier list geral (só quem finalizou), ou None se ninguém finalizou."""
        if not self.finalizados:
            return None
        return tier_geral({j["id"]: self.faixas_de(j["id"]) for j in self.finalizados},
                          list(self.itens))

    def lista(self, faixas_por_item, ordem=None):
        """Monta a tier list no formato das telas: {"tier_list": [...], "pulados": [...]}."""
        por_faixa = [[] for _ in self.faixas]
        pulados = []
        for item_id in ordem or list(self.itens):
            if item_id not in faixas_por_item:
                continue                      # ainda sem resposta
            item = self.itens[item_id]
            dados = {"id": item_id, "nome": item["nome"], "imagem": item["imagem"], "novo": False}
            faixa = faixas_por_item[item_id]
            if faixa is None:
                pulados.append(dados)
            else:
                por_faixa[faixa].append(dados)
        return {"tier_list": por_faixa, "pulados": pulados}


# ===========================================================================
# 4. Mudanças de estado (sempre dentro de banco.transacao)
# ===========================================================================

def _conferir_pode_responder(situacao, jogador):
    if situacao.partida["modo"] != "individual":
        raise AcaoInvalida("Esta ação é do modo individual.")
    if situacao.estado != "aberta":
        raise AcaoInvalida("A partida foi encerrada. A tela foi atualizada.")
    if situacao.jogador(jogador["id"])["finalizado_em"] is not None:
        raise AcaoInvalida("Você já finalizou: as respostas estão travadas.")


def responder(con, jogador, item_id, faixa, revisao, agora):
    """Salva (ou troca) a resposta de um item: uma faixa, ou None para "pulei".

    `revisao` é a revisão da resposta que estava na tela; se o servidor já
    tiver outra (um envio antigo chegou atrasado), a resposta é recusada.
    """
    situacao = Situacao(con, jogador["partida_id"])
    _conferir_pode_responder(situacao, jogador)
    if item_id not in situacao.itens:
        raise AcaoInvalida("Esse item não é desta partida.", status=400)
    if faixa is not None and not 0 <= faixa < len(situacao.faixas):
        raise AcaoInvalida("Faixa inválida.", status=400)
    atual = situacao.respostas[jogador["id"]].get(item_id)
    if revisao != (atual[1] if atual else 0):
        raise AcaoInvalida("Essa resposta já tinha mudado por outro envio. A tela foi atualizada.")
    con.execute(
        "INSERT INTO votos (item_id, jogador_id, faixa_indice, votado_em, revisao)"
        " VALUES (?, ?, ?, ?, 1)"
        " ON CONFLICT (item_id, jogador_id) DO UPDATE SET"
        " faixa_indice = excluded.faixa_indice, votado_em = excluded.votado_em,"
        " revisao = votos.revisao + 1",
        (item_id, jogador["id"], faixa, agora),
    )
    subir_versao(con, jogador["partida_id"])


def finalizar(con, jogador, agora):
    """Trava as respostas do jogador. Só vale com todos os itens respondidos."""
    situacao = Situacao(con, jogador["partida_id"])
    _conferir_pode_responder(situacao, jogador)
    faltam = len(situacao.itens) - len(situacao.respostas[jogador["id"]])
    if faltam:
        raise AcaoInvalida(f"Ainda falta responder {faltam} item(ns).")
    con.execute(
        "UPDATE jogadores SET finalizado_em = ? WHERE id = ? AND finalizado_em IS NULL",
        (agora, jogador["id"]),
    )
    subir_versao(con, jogador["partida_id"])
    verificar_encerramento(con, jogador["partida_id"])


def verificar_encerramento(con, partida_id):
    """aberta -> encerrada quando todos os jogadores ativos finalizaram.

    Chamada depois de cada "finalizar" e de cada remoção (remover o único que
    faltava encerra a partida). Devolve True se encerrou agora.
    """
    cursor = con.execute(
        "UPDATE partidas SET estado = 'encerrada', versao = versao + 1"
        " WHERE id = ? AND modo = 'individual' AND estado = 'aberta'"
        " AND NOT EXISTS (SELECT 1 FROM jogadores WHERE partida_id = partidas.id"
        "                 AND removido_em IS NULL AND finalizado_em IS NULL)",
        (partida_id,),
    )
    return cursor.rowcount == 1


def encerrar(con, partida_id):
    """Botão "Encerrar e revelar" do admin. Devolve True se encerrou agora
    (False se a partida não é individual ou já estava encerrada)."""
    cursor = con.execute(
        "UPDATE partidas SET estado = 'encerrada', versao = versao + 1"
        " WHERE id = ? AND modo = 'individual' AND estado = 'aberta'",
        (partida_id,),
    )
    return cursor.rowcount == 1


# ===========================================================================
# 5. Estado para as telas (JSON)
# ===========================================================================

def montar_estado(con, partida_id, jogador_id=None, para_admin=False):
    """JSON do modo individual.

    Visibilidade (vale para a tela e para a API, inclusive o campo "versao"):
    - quem ainda NÃO finalizou, com a partida aberta, recebe só os próprios
      itens e respostas: nada dos outros (nem nomes, nem contagens, nem a geral);
    - quem finalizou, e todos depois de encerrada, recebem a geral (só com quem
      finalizou), as listas de quem finalizou, com nome, e a própria
      compatibilidade (se tiver finalizado);
    - o admin vê tudo, inclusive o progresso e as listas de cada um.
    """
    situacao = Situacao(con, partida_id)
    estado = {
        "versao": versao_do_estado(situacao.partida["versao"], set()),
        "modo": "individual",
        "estado": situacao.estado,
        "tema": situacao.partida["tema_nome"],
        "total_itens": len(situacao.itens),
        "faixas": situacao.faixas,
    }

    if jogador_id is not None:
        eu = situacao.jogador(jogador_id)
        finalizei = eu["finalizado_em"] is not None
        estado["eu"] = {
            "nome": eu["nome"],
            "finalizado": finalizei,
            "respondidos": len(situacao.respostas[jogador_id]),
        }
        if situacao.estado == "aberta" and not finalizei:
            # Preenchendo: só os próprios itens, na ordem sorteada para ele.
            estado["itens"] = [
                _item_para_preencher(situacao, jogador_id, item_id)
                for item_id in situacao.ordem_de(jogador_id)
            ]
            estado["resultado"] = None
        else:
            estado["itens"] = None
            estado["resultado"] = _resultado(situacao, jogador_id if finalizei else None)
        estado["versao"] = _versao_do_conteudo(estado)
        return estado

    if para_admin:
        estado["jogadores"] = [_jogador_para_admin(situacao, j) for j in situacao.jogadores]
        geral = situacao.geral()
        estado["geral"] = situacao.lista(geral) if geral is not None else None
    return estado


def _versao_do_conteudo(estado):
    """Versão da tela do jogador tirada do próprio conteúdo que ele recebe.

    A versão da partida sobe a cada resposta de QUALQUER jogador. Se fosse
    mandada ao jogador, quem ainda está preenchendo poderia contar pela API as
    respostas dos outros (e a tela dele seria redesenhada à toa). Assim, a
    versão só muda quando muda algo que ele pode ver.
    """
    conteudo = json.dumps({k: v for k, v in estado.items() if k != "versao"},
                          sort_keys=True, ensure_ascii=False)
    return "j." + hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]


def _item_para_preencher(situacao, jogador_id, item_id):
    item = situacao.itens[item_id]
    resposta = situacao.respostas[jogador_id].get(item_id)
    return {
        "id": item_id,
        "nome": item["nome"],
        "imagem": item["imagem"],
        "respondido": resposta is not None,
        "faixa": resposta[0] if resposta else None,     # None também = "pulei"
        "revisao": resposta[1] if resposta else 0,
    }


def _resultado(situacao, meu_id):
    """Parte liberada depois de finalizar (ou para todos, depois de encerrada)."""
    geral = situacao.geral()
    resultado = {
        "geral": situacao.lista(geral) if geral is not None else None,
        "minha": None,
        "compatibilidade": None,
        "outros": [
            {"nome": j["nome"], **situacao.lista(situacao.faixas_de(j["id"]), situacao.ordem_de(j["id"]))}
            for j in situacao.finalizados if j["id"] != meu_id
        ],
        # Só enquanto a partida está aberta: quem ainda não finalizou.
        "faltam": [j["nome"] for j in situacao.ativos if j["finalizado_em"] is None]
        if situacao.estado == "aberta" else [],
    }
    if meu_id is not None:
        minhas = situacao.faixas_de(meu_id)
        resultado["minha"] = situacao.lista(minhas, situacao.ordem_de(meu_id))
        resultado["compatibilidade"] = compatibilidade(minhas, geral or {}, len(situacao.faixas))
    return resultado


def _jogador_para_admin(situacao, jogador):
    dados = {
        "id": jogador["id"],
        "nome": jogador["nome"],
        "entrou": jogador["visto_em"] is not None,
        "removido": jogador["removido_em"] is not None,
        "finalizado": jogador["finalizado_em"] is not None,
        "respondidos": len(situacao.respostas[jogador["id"]]),
        "lista": None,
    }
    if not dados["removido"]:
        # O admin pode ver a lista de cada um (decisão do dono), inclusive
        # de quem ainda está preenchendo.
        dados["lista"] = situacao.lista(situacao.faixas_de(jogador["id"]),
                                        situacao.ordem_de(jogador["id"]))
    return dados

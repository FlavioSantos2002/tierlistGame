"""Motor do jogo: regras da partida e mudanças de estado (modo ao vivo).

Estados da partida ao vivo:
    espera -> (votacao <-> resultado) x N rodadas -> encerrada
O modo individual ("cada um no seu ritmo") fica em individual.py; aqui só há
o que é comum aos dois (regra da maioria, remover jogador) e o despacho de
montar_estado para o módulo certo.

O arquivo tem duas partes:
1. Regras puras (sem banco): calcular_faixa, pode_fechar_votacao e
   pode_avancar_resultado. São as regras do jogo e são fáceis de testar.
2. Funções que leem e gravam no banco. TODAS devem ser chamadas dentro de
   `banco.transacao(con)` (BEGIN IMMEDIATE). Como só uma transação de escrita
   roda por vez, e cada mudança confere o estado atual antes de mudar,
   a rodada nunca fecha nem avança duas vezes.
"""
import zlib
from collections import Counter
from dataclasses import dataclass

# Um jogador é "online" se foi visto (fez polling ou ação) nos últimos 15 segundos.
ONLINE_SEGUNDOS = 15

# Como cada estado aparece nas telas.
NOMES_DOS_ESTADOS = {
    "espera": "Aguardando início",
    "votacao": "Votação",
    "resultado": "Resultado",
    "aberta": "Aberta",
    "encerrada": "Encerrada",
}


class AcaoInvalida(Exception):
    """Ação do jogador que não vale agora.

    `status` é o código HTTP da resposta: 409 quando a partida está em outra
    fase/rodada (o jogador vê o estado atualizado), 400 quando os dados vieram errados.
    """

    def __init__(self, mensagem, status=409):
        super().__init__(mensagem)
        self.status = status


# ===========================================================================
# 1. Regras puras
# ===========================================================================

def calcular_faixa(votos):
    """Índice da faixa do item a partir dos índices votados (0 = melhor).

    Regra da maioria: a faixa com mais votos. Empate: vai para a PIOR faixa
    entre as empatadas (maior índice). Abstenções não entram na lista.
    Sem votos, devolve None (o item fica "pulado").

    Exemplos (0 = S ... 4 = D): [1, 1, 2, 2] -> 2 (B);  [0, 0, 4, 4] -> 4 (D);
    [0, 2, 3] -> 3 (C).
    """
    if not votos:
        return None
    contagem = Counter(votos)
    mais_votos = max(contagem.values())
    return max(faixa for faixa, quantidade in contagem.items() if quantidade == mais_votos)


def pode_fechar_votacao(ids_jogadores, ids_online, ids_que_votaram, ids_que_pularam):
    """A votação fecha quando:
    a) todos os jogadores da partida votaram (online ou não); ou
    b) há pelo menos 1 jogador online e todos os online votaram ou pularam.
    """
    todos = set(ids_jogadores)
    if todos and todos <= set(ids_que_votaram):
        return True
    online = set(ids_online)
    agiram = set(ids_que_votaram) | set(ids_que_pularam)
    return bool(online) and online <= agiram


def pode_avancar_resultado(ids_online, ids_que_continuaram):
    """O resultado avança quando há pelo menos 1 jogador online
    e todos os online apertaram "Continuar"."""
    online = set(ids_online)
    return bool(online) and online <= set(ids_que_continuaram)


def ids_online(jogadores, agora):
    """Ids dos jogadores vistos nos últimos ONLINE_SEGUNDOS."""
    limite = agora - ONLINE_SEGUNDOS
    return {
        j["id"] for j in jogadores
        if j["visto_em"] is not None and j["visto_em"] >= limite
    }


def versao_do_estado(versao_banco, online):
    """Texto que muda sempre que a tela precisa ser redesenhada.

    A versão do banco sobe a cada ação e mudança de fase. Mas alguém ficar
    offline não grava nada no banco, então juntamos um resumo (crc32) do
    conjunto de jogadores online.
    """
    resumo_online = zlib.crc32(",".join(str(i) for i in sorted(online)).encode())
    return f"{versao_banco}.{resumo_online:08x}"


# ===========================================================================
# 2. Leitura da fase atual (poucas consultas simples, usadas a cada polling)
# ===========================================================================

@dataclass
class Fase:
    partida: dict
    faixas: list
    jogadores: list             # todos, inclusive removidos (o admin vê a lista inteira)
    item: dict | None           # item da rodada atual (None na espera)
    votos: dict                 # SÓ jogadores ativos: jogador_id -> faixa, ou None se pulou
    continuaram: set            # SÓ ativos: ids de quem apertou "Continuar" nesta rodada
    revisoes: dict              # jogador_id -> revisão do voto/abstenção (sem linha = 0)

    @property
    def ativos(self):
        """Jogadores que não foram removidos: só eles contam nas regras."""
        return [j for j in self.jogadores if j["removido_em"] is None]

    @property
    def estado(self):
        return self.partida["estado"]

    @property
    def rodada(self):
        return self.partida["rodada_atual"]

    @property
    def ids_que_votaram(self):
        return {jid for jid, faixa in self.votos.items() if faixa is not None}

    @property
    def ids_que_pularam(self):
        return {jid for jid, faixa in self.votos.items() if faixa is None}


def ler_fase(con, partida_id):
    """Lê tudo que as regras precisam sobre a rodada atual. None se a partida não existe."""
    partida = con.execute("SELECT * FROM partidas WHERE id = ?", (partida_id,)).fetchone()
    if partida is None:
        return None
    faixas = con.execute(
        "SELECT indice, rotulo, descricao, cor FROM faixas WHERE partida_id = ? ORDER BY indice",
        (partida_id,),
    ).fetchall()
    jogadores = con.execute(
        "SELECT id, nome, visto_em, removido_em FROM jogadores WHERE partida_id = ? ORDER BY id",
        (partida_id,),
    ).fetchall()

    item = None
    votos = {}
    revisoes = {}
    continuaram = set()
    if partida["rodada_atual"] > 0:
        item = con.execute(
            "SELECT * FROM itens WHERE partida_id = ? AND rodada = ?",
            (partida_id, partida["rodada_atual"]),
        ).fetchone()
        # Votos e "continuar" de jogadores removidos não contam em nada.
        for linha in con.execute(
            "SELECT v.jogador_id, v.faixa_indice, v.revisao FROM votos v"
            " JOIN jogadores j ON j.id = v.jogador_id"
            " WHERE v.item_id = ? AND j.removido_em IS NULL",
            (item["id"],),
        ):
            votos[linha["jogador_id"]] = linha["faixa_indice"]
            revisoes[linha["jogador_id"]] = linha["revisao"]
        continuaram = {
            linha["jogador_id"]
            for linha in con.execute(
                "SELECT c.jogador_id FROM continuar c JOIN jogadores j ON j.id = c.jogador_id"
                " WHERE c.item_id = ? AND j.removido_em IS NULL",
                (item["id"],),
            )
        }
    return Fase(dict(partida), faixas, jogadores, item and dict(item), votos, continuaram, revisoes)


def subir_versao(con, partida_id):
    con.execute("UPDATE partidas SET versao = versao + 1 WHERE id = ?", (partida_id,))


# ===========================================================================
# 3. Mudanças de estado (sempre dentro de banco.transacao)
# ===========================================================================

def iniciar(con, partida_id):
    """espera -> votacao da rodada 1. Devolve True se mudou."""
    cursor = con.execute(
        "UPDATE partidas SET estado = 'votacao', rodada_atual = 1, versao = versao + 1"
        " WHERE id = ? AND estado = 'espera' AND modo = 'ao_vivo'",
        (partida_id,),
    )
    return cursor.rowcount == 1


def fechar_votacao(con, partida_id, rodada):
    """votacao -> resultado: calcula a faixa do item (ou marca como pulado).

    O WHERE confere estado e rodada; se outra requisição já fechou esta
    rodada, nada muda e devolve False.
    """
    cursor = con.execute(
        "UPDATE partidas SET estado = 'resultado', versao = versao + 1"
        " WHERE id = ? AND estado = 'votacao' AND rodada_atual = ?",
        (partida_id, rodada),
    )
    if cursor.rowcount != 1:
        return False

    item = con.execute(
        "SELECT id FROM itens WHERE partida_id = ? AND rodada = ?", (partida_id, rodada)
    ).fetchone()
    # Só votos de jogadores ativos (abstenções também ficam de fora).
    votos = [
        linha["faixa_indice"]
        for linha in con.execute(
            "SELECT v.faixa_indice FROM votos v JOIN jogadores j ON j.id = v.jogador_id"
            " WHERE v.item_id = ? AND v.faixa_indice IS NOT NULL AND j.removido_em IS NULL",
            (item["id"],),
        )
    ]
    faixa = calcular_faixa(votos)
    situacao = "pulado" if faixa is None else "classificado"
    con.execute(
        "UPDATE itens SET situacao = ?, faixa_indice = ? WHERE id = ?",
        (situacao, faixa, item["id"]),
    )
    return True


def avancar_rodada(con, partida_id, rodada):
    """resultado -> votacao da próxima rodada, ou -> encerrada se era a última.

    Devolve False (sem mudar nada) se a partida já não está no resultado desta rodada.
    """
    partida = con.execute(
        "SELECT total_rodadas FROM partidas WHERE id = ? AND estado = 'resultado' AND rodada_atual = ?",
        (partida_id, rodada),
    ).fetchone()
    if partida is None:
        return False
    if rodada < partida["total_rodadas"]:
        con.execute(
            "UPDATE partidas SET estado = 'votacao', rodada_atual = ?, versao = versao + 1"
            " WHERE id = ?",
            (rodada + 1, partida_id),
        )
    else:
        con.execute(
            "UPDATE partidas SET estado = 'encerrada', versao = versao + 1 WHERE id = ?",
            (partida_id,),
        )
    return True


def verificar_avanco(con, partida_id, agora):
    """Fecha a votação ou avança o resultado se as regras permitirem.

    Chamada depois de cada voto, pulo e continuar, e também em cada polling
    (alguém ficar offline pode ser o que libera o avanço). Devolve True se mudou.
    """
    fase = ler_fase(con, partida_id)
    if fase is None or fase.partida["modo"] != "ao_vivo":
        return False                             # o modo individual não usa presença
    online = ids_online(fase.ativos, agora)       # removidos nunca contam como online

    if fase.estado == "votacao":
        if pode_fechar_votacao(
            [j["id"] for j in fase.ativos], online, fase.ids_que_votaram, fase.ids_que_pularam
        ):
            return fechar_votacao(con, partida_id, fase.rodada)
    elif fase.estado == "resultado":
        if pode_avancar_resultado(online, fase.continuaram):
            return avancar_rodada(con, partida_id, fase.rodada)
    return False


def forcar_avanco(con, partida_id, estado_esperado, rodada_esperada):
    """Botão "Forçar avanço" do admin.

    O formulário manda a fase que o admin estava vendo. Se a partida já saiu
    dessa fase (clique duplo, aba antiga), nada acontece: assim um clique
    nunca pula duas fases.
    """
    partida = con.execute(
        "SELECT estado, rodada_atual FROM partidas WHERE id = ?", (partida_id,)
    ).fetchone()
    if partida is None:
        return False
    if partida["estado"] != estado_esperado or partida["rodada_atual"] != rodada_esperada:
        return False
    if partida["estado"] == "votacao":
        return fechar_votacao(con, partida_id, rodada_esperada)
    if partida["estado"] == "resultado":
        return avancar_rodada(con, partida_id, rodada_esperada)
    return False


def remover_jogador(con, partida_id, jogador_id, agora):
    """Botão "Remover" do admin: tira o jogador da partida, para sempre.

    O jogador continua no banco (com removido_em preenchido), mas deixa de
    contar em todas as regras, e os votos dele saem da rodada em andamento.
    Rodadas que já fecharam ficam como estão (decisão do dono do projeto).
    Logo depois, as regras de fechamento/avanço são reavaliadas: remover
    quem estava travando a rodada libera a partida na hora.

    No modo individual, remover o único que ainda não tinha finalizado
    encerra a partida.
    Depois que a partida termina, ninguém mais é removido: o resultado final
    não muda.

    Devolve True se removeu (False se ele já estava removido).
    """
    partida = con.execute(
        "SELECT modo, estado FROM partidas WHERE id = ?", (partida_id,)
    ).fetchone()
    if partida is not None and partida["estado"] == "encerrada":
        raise AcaoInvalida("A partida já terminou; o resultado final não muda mais.")
    jogador = con.execute(
        "SELECT id, removido_em FROM jogadores WHERE id = ? AND partida_id = ?",
        (jogador_id, partida_id),
    ).fetchone()
    if jogador is None:
        raise AcaoInvalida("Esse jogador não é desta partida.", status=404)
    if jogador["removido_em"] is not None:
        return False
    ativos = con.execute(
        "SELECT COUNT(*) FROM jogadores WHERE partida_id = ? AND removido_em IS NULL",
        (partida_id,),
    ).fetchone()[0]
    if ativos <= 1:
        raise AcaoInvalida("Não dá para remover o último jogador ativo da partida.")
    con.execute("UPDATE jogadores SET removido_em = ? WHERE id = ?", (agora, jogador_id))
    # Voto (ou abstenção) dele na rodada que ainda está aberta: descartado.
    # Assim a contagem mostrada no resultado continua batendo com a faixa.
    # Votos de rodadas já fechadas ficam como estão.
    con.execute(
        "DELETE FROM votos WHERE jogador_id = ? AND item_id IN ("
        "  SELECT i.id FROM itens i JOIN partidas p ON p.id = i.partida_id"
        "  WHERE p.id = ? AND p.estado = 'votacao' AND i.rodada = p.rodada_atual)",
        (jogador_id, partida_id),
    )
    subir_versao(con, partida_id)
    if partida["modo"] == "individual":
        # Importado aqui dentro porque individual.py importa este arquivo.
        from individual import verificar_encerramento
        verificar_encerramento(con, partida_id)
    else:
        verificar_avanco(con, partida_id, agora)
    return True


# ===========================================================================
# 4. Ações do jogador (sempre dentro de banco.transacao)
# ===========================================================================

def registrar_presenca(con, jogador, agora):
    """Marca o jogador como visto agora. Na primeira vez, sobe a versão
    (a lista "quem já entrou" mudou)."""
    con.execute("UPDATE jogadores SET visto_em = ? WHERE id = ?", (agora, jogador["id"]))
    if jogador["visto_em"] is None:
        subir_versao(con, jogador["partida_id"])


def _conferir_fase(fase, estado, rodada):
    """Recusa ações feitas numa fase/rodada que já passou (ex.: tela desatualizada)."""
    if fase.partida["modo"] != "ao_vivo":
        raise AcaoInvalida("Esta ação é do modo ao vivo.")
    if fase.estado != estado or fase.rodada != rodada:
        raise AcaoInvalida("A partida já está em outra fase. A tela foi atualizada.")


def _conferir_revisao(fase, jogador, revisao):
    """Recusa um voto/pulo feito em cima de uma escolha que já mudou.

    Exemplo: o jogador vota S, o pedido demora (o navegador desiste), ele vota A
    e o A é aceito. Se depois o pedido do S chegar ao servidor, ele ainda traz
    a revisão antiga e é recusado: o A continua valendo.
    """
    if revisao != fase.revisoes.get(jogador["id"], 0):
        raise AcaoInvalida("Seu voto já tinha mudado por outro envio. A tela foi atualizada.")


def votar(con, jogador, rodada, faixa, revisao, agora):
    fase = ler_fase(con, jogador["partida_id"])
    _conferir_fase(fase, "votacao", rodada)
    if not 0 <= faixa < len(fase.faixas):
        raise AcaoInvalida("Faixa inválida.", status=400)
    _conferir_revisao(fase, jogador, revisao)
    # Upsert: o primeiro voto insere (revisão 1); votar de novo troca o voto
    # (e também substitui uma abstenção) e soma 1 à revisão.
    con.execute(
        "INSERT INTO votos (item_id, jogador_id, faixa_indice, votado_em, revisao)"
        " VALUES (?, ?, ?, ?, 1)"
        " ON CONFLICT (item_id, jogador_id) DO UPDATE SET"
        " faixa_indice = excluded.faixa_indice, votado_em = excluded.votado_em,"
        " revisao = votos.revisao + 1",
        (fase.item["id"], jogador["id"], faixa, agora),
    )
    subir_versao(con, jogador["partida_id"])


def pular(con, jogador, rodada, revisao, agora):
    """Abstenção neste item. Só existe ANTES de votar."""
    fase = ler_fase(con, jogador["partida_id"])
    _conferir_fase(fase, "votacao", rodada)
    _conferir_revisao(fase, jogador, revisao)
    if fase.votos.get(jogador["id"]) is not None:
        raise AcaoInvalida("Você já votou neste item; não dá para pular depois de votar.")
    # Primeira abstenção: revisão 1. Pular de novo não muda nada (nem a revisão).
    cursor = con.execute(
        "INSERT INTO votos (item_id, jogador_id, faixa_indice, votado_em, revisao)"
        " VALUES (?, ?, NULL, ?, 1)"
        " ON CONFLICT (item_id, jogador_id) DO NOTHING",
        (fase.item["id"], jogador["id"], agora),
    )
    if cursor.rowcount:
        subir_versao(con, jogador["partida_id"])


def continuar(con, jogador, rodada):
    fase = ler_fase(con, jogador["partida_id"])
    _conferir_fase(fase, "resultado", rodada)
    cursor = con.execute(
        "INSERT INTO continuar (item_id, jogador_id) VALUES (?, ?)"
        " ON CONFLICT (item_id, jogador_id) DO NOTHING",
        (fase.item["id"], jogador["id"]),
    )
    if cursor.rowcount:
        subir_versao(con, jogador["partida_id"])


# ===========================================================================
# 5. Estado para as telas (JSON do polling)
# ===========================================================================

def montar_estado(con, partida_id, agora, jogador_id=None, para_admin=False):
    """Monta o dicionário que vira o JSON de /api/estado.

    Votos são anônimos: ninguém recebe o voto de outro jogador. O jogador vê
    só contagens; o admin vê quem já agiu (não em quê votou).
    Partidas do modo individual são montadas por individual.montar_estado.
    """
    modo = con.execute("SELECT modo FROM partidas WHERE id = ?", (partida_id,)).fetchone()["modo"]
    if modo == "individual":
        from individual import montar_estado as montar_individual   # (import circular)
        return montar_individual(con, partida_id, jogador_id=jogador_id, para_admin=para_admin)
    fase = ler_fase(con, partida_id)
    online = ids_online(fase.ativos, agora)      # removidos não entram em nenhuma conta

    if fase.estado == "votacao":
        agiram = set(fase.votos)                 # votou ou pulou (só ativos)
    elif fase.estado == "resultado":
        agiram = fase.continuaram
    else:
        agiram = set()

    estado = {
        "versao": versao_do_estado(fase.partida["versao"], online),
        "estado": fase.estado,
        "tema": fase.partida["tema_nome"],
        "rodada": fase.rodada,
        "total_rodadas": fase.partida["total_rodadas"],
        "faixas": [dict(f) for f in fase.faixas],
        "item": None,
        "presenca": {
            "online": len(online),
            "offline": len(fase.ativos) - len(online),
            "faltam": len(online - agiram),     # online que ainda não agiram nesta fase
        },
        "distribuicao": None,
        "abstencoes": None,
    }
    estado.update(_tier_list(con, fase))

    if fase.estado in ("votacao", "resultado"):
        estado["item"] = {"nome": fase.item["nome"], "imagem": fase.item["imagem"]}

    if fase.estado == "resultado":
        # Contagem de votos por faixa deste item (anônima). A rodada já fechou:
        # a contagem é a do fechamento. Quem foi removido antes de fechar teve o
        # voto apagado (remover_jogador); quem foi removido depois continua
        # contado, porque rodadas fechadas ficam como estão (decisão do dono).
        contagem = [0] * len(fase.faixas)
        abstencoes = 0
        for linha in con.execute(
            "SELECT faixa_indice FROM votos WHERE item_id = ?", (fase.item["id"],)
        ):
            if linha["faixa_indice"] is None:
                abstencoes += 1
            else:
                contagem[linha["faixa_indice"]] += 1
        estado["distribuicao"] = contagem
        estado["abstencoes"] = abstencoes

    if jogador_id is not None:
        eu = next(j for j in fase.jogadores if j["id"] == jogador_id)
        estado["eu"] = {
            "nome": eu["nome"],
            "voto": fase.votos.get(jogador_id),
            "pulou": jogador_id in fase.ids_que_pularam,
            "continuou": jogador_id in fase.continuaram,
            # Vai de volta no próximo votar/pular (ver _conferir_revisao).
            "revisao": fase.revisoes.get(jogador_id, 0),
        }
        if fase.estado == "espera":
            estado["entraram"] = [j["nome"] for j in fase.ativos if j["visto_em"] is not None]

    if para_admin:
        # O admin vê todos, inclusive os removidos (marcados), e o id de cada
        # um para o botão "Remover".
        estado["jogadores"] = [
            {
                "id": j["id"],
                "nome": j["nome"],
                "entrou": j["visto_em"] is not None,
                "online": j["id"] in online,
                "removido": j["removido_em"] is not None,
                "acao": _acao_na_fase(fase, j["id"]),
            }
            for j in fase.jogadores
        ]
    return estado


def _acao_na_fase(fase, jogador_id):
    """O que o jogador já fez na fase atual: "votou", "pulou", "continuou" ou None."""
    if fase.estado == "votacao" and jogador_id in fase.votos:
        return "pulou" if fase.votos[jogador_id] is None else "votou"
    if fase.estado == "resultado" and jogador_id in fase.continuaram:
        return "continuou"
    return None


def _tier_list(con, fase):
    """Itens já decididos: classificados por faixa (na ordem das rodadas) e pulados.

    No resultado, o item da rodada atual vem com "novo": true (para destacar).
    """
    por_faixa = [[] for _ in fase.faixas]
    pulados = []
    for item in con.execute(
        "SELECT rodada, nome, imagem, situacao, faixa_indice FROM itens"
        " WHERE partida_id = ? AND situacao != 'pendente' ORDER BY rodada",
        (fase.partida["id"],),
    ):
        dados = {
            "nome": item["nome"],
            "imagem": item["imagem"],
            "novo": fase.estado == "resultado" and item["rodada"] == fase.rodada,
        }
        if item["situacao"] == "classificado":
            por_faixa[item["faixa_indice"]].append(dados)
        else:
            pulados.append(dados)
    return {"tier_list": por_faixa, "pulados": pulados}

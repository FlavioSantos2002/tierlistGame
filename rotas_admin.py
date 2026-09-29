"""Rotas do painel do admin: login, lista de partidas, nova partida e tela da partida."""
import random
import re
import secrets
import time
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import banco
import individual
import jogo
import temas
from endereco import endereco_publico

admin = Blueprint("admin", __name__, url_prefix="/admin")

RODADAS_PADRAO = 12
MODOS = {"ao_vivo": "Ao vivo", "individual": "Cada um no seu ritmo"}
MIN_FAIXAS, MAX_FAIXAS = 2, 7
MIN_JOGADORES, MAX_JOGADORES = 2, 20
TAMANHO_MAX_ROTULO = 3
TAMANHO_MAX_DESCRICAO = 40
TAMANHO_MAX_NOME_JOGADOR = 30
COR_VALIDA = re.compile(r"^#[0-9a-fA-F]{6}$")

FAIXAS_PADRAO = [
    {"rotulo": "S", "descricao": "Perfeito", "cor": "#ff7f7f"},
    {"rotulo": "A", "descricao": "Muito bom", "cor": "#ffbf7f"},
    {"rotulo": "B", "descricao": "Bom", "cor": "#ffdf7f"},
    {"rotulo": "C", "descricao": "Fraco", "cor": "#ffff7f"},
    {"rotulo": "D", "descricao": "Ruim", "cor": "#bfff7f"},
]


# ---------------------------------------------------------------------------
# Segurança: CSRF e login
# ---------------------------------------------------------------------------

def token_csrf():
    """Token CSRF guardado na sessão (criado na primeira vez que é pedido)."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def textos_iguais(a, b):
    """Compara dois textos em tempo constante (evita descobrir a senha pelo tempo de resposta)."""
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@admin.app_context_processor
def disponibilizar_csrf():
    # Permite escrever {{ token_csrf() }} nos templates.
    return {"token_csrf": token_csrf}


@admin.before_request
def conferir_csrf():
    """Todo POST do painel (inclusive o login) precisa trazer o token da sessão."""
    if request.method == "POST":
        enviado = request.form.get("csrf_token", "")
        esperado = session.get("csrf", "")
        if not esperado or not textos_iguais(enviado, esperado):
            abort(400, "O formulário expirou. Volte, recarregue a página e tente de novo.")


def exige_admin(funcao):
    """Decorador: manda para a tela de login quem não está logado."""
    @wraps(funcao)
    def protegida(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.entrar"))
        return funcao(*args, **kwargs)
    return protegida


@admin.route("/entrar", methods=["GET", "POST"])
def entrar():
    erro = None
    if request.method == "POST":
        digitado = request.form.get("token", "")
        if textos_iguais(digitado, current_app.config["ADMIN_TOKEN"]):
            session.clear()  # começa uma sessão nova, com token CSRF novo
            session["admin"] = True
            token_csrf()
            return redirect(url_for("admin.lista"))
        erro = "Token incorreto."
    return render_template("admin_entrar.html", erro=erro)


@admin.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("admin.entrar"))


# ---------------------------------------------------------------------------
# Lista de partidas
# ---------------------------------------------------------------------------

@admin.route("/")
@exige_admin
def lista():
    partidas = banco.obter().execute(
        "SELECT id, tema_nome, modo, estado, rodada_atual, total_rodadas, criada_em"
        " FROM partidas ORDER BY id DESC"
    ).fetchall()
    return render_template("admin_lista.html", partidas=partidas)


@admin.route("/partida/<int:partida_id>/apagar", methods=["POST"])
@exige_admin
def apagar(partida_id):
    con = banco.obter()
    with banco.transacao(con):
        # ON DELETE CASCADE apaga faixas, jogadores, itens, votos e "continuar".
        con.execute("DELETE FROM partidas WHERE id = ?", (partida_id,))
    flash("Partida apagada.")
    return redirect(url_for("admin.lista"))


# ---------------------------------------------------------------------------
# Nova partida
# ---------------------------------------------------------------------------

@admin.route("/nova", methods=["GET", "POST"])
@exige_admin
def nova():
    # O arquivo é lido de novo a cada abertura (e a cada envio) desta tela.
    lista_temas, erro_arquivo = temas.carregar(current_app.config["TEMAS_PATH"])
    validos = {tema["nome"]: tema for tema in lista_temas if tema["valido"]}

    formulario = {"modo": "ao_vivo", "tema": "", "rodadas": RODADAS_PADRAO,
                  "faixas": FAIXAS_PADRAO, "jogadores": ""}
    erros = []

    if request.method == "POST" and not erro_arquivo:
        formulario, erros, dados = ler_formulario(request.form, validos)
        if not erros:
            partida_id = criar_partida(**dados)
            flash("Partida criada! Mande a cada jogador o link dele.")
            return redirect(url_for("admin.partida", partida_id=partida_id))

    return render_template(
        "admin_nova.html",
        erro_arquivo=erro_arquivo,
        temas=lista_temas,
        # Só os temas válidos vão para o JavaScript da prévia.
        temas_validos=[
            {"nome": t["nome"], "itens": t["itens"], "assinatura": t["assinatura"]}
            for t in validos.values()
        ],
        formulario=formulario,
        erros=erros,
        min_faixas=MIN_FAIXAS,
        max_faixas=MAX_FAIXAS,
        max_rotulo=TAMANHO_MAX_ROTULO,
        max_descricao=TAMANHO_MAX_DESCRICAO,
        min_jogadores=MIN_JOGADORES,
        max_jogadores=MAX_JOGADORES,
        max_nome_jogador=TAMANHO_MAX_NOME_JOGADOR,
    )


def ler_formulario(campos, validos):
    """Valida o formulário de nova partida.

    Devolve (formulario, erros, dados):
    - formulario: valores para preencher a tela de novo se houver erro;
    - erros: lista de mensagens (vazia se estiver tudo certo);
    - dados: valores limpos para `criar_partida`.
    """
    erros = []

    # 0. Modo ("ao vivo" é o padrão, como na versão 1)
    modo = campos.get("modo", "ao_vivo")
    if modo not in MODOS:
        erros.append("Escolha um modo válido.")

    # 1. Tema
    nome_tema = campos.get("tema", "")
    tema = validos.get(nome_tema)
    if tema is None:
        erros.append("Escolha um tema válido (o temas.json pode ter mudado).")
    elif not campos.get("assinatura_tema"):
        erros.append("A prévia do tema não foi carregada. O JavaScript está ligado?")
    elif campos.get("assinatura_tema") != tema["assinatura"]:
        erros.append(
            "O tema mudou no temas.json depois que a prévia foi aberta. "
            "Confira a prévia atualizada e clique em Criar partida de novo."
        )

    # 2. Rodadas
    texto_rodadas = campos.get("rodadas", "").strip()
    try:
        rodadas = int(texto_rodadas)
    except ValueError:
        rodadas = None
        erros.append("O número de rodadas precisa ser um número inteiro.")
    if rodadas is not None and tema is not None:
        total_itens = len(tema["itens"])
        if not 1 <= rodadas <= total_itens:
            erros.append(f"As rodadas precisam estar entre 1 e {total_itens} (itens do tema).")

    # 3. Faixas (os campos vêm repetidos, uma vez por faixa, na ordem da tela)
    rotulos = campos.getlist("faixa_rotulo")
    descricoes = campos.getlist("faixa_descricao")
    cores = campos.getlist("faixa_cor")
    if not len(rotulos) == len(descricoes) == len(cores):
        erros.append("Os campos das faixas vieram incompletos. Recarregue a página.")
    faixas = [
        {"rotulo": r.strip(), "descricao": d.strip(), "cor": c.strip()}
        for r, d, c in zip(rotulos, descricoes, cores)
    ]
    if not MIN_FAIXAS <= len(faixas) <= MAX_FAIXAS:
        erros.append(f"Use de {MIN_FAIXAS} a {MAX_FAIXAS} faixas.")
    rotulos_vistos = set()
    for numero, faixa in enumerate(faixas, start=1):
        if not faixa["rotulo"]:
            erros.append(f"Faixa {numero}: o rótulo está vazio.")
        elif len(faixa["rotulo"]) > TAMANHO_MAX_ROTULO:
            erros.append(f"Faixa {numero}: o rótulo pode ter até {TAMANHO_MAX_ROTULO} caracteres.")
        elif faixa["rotulo"].casefold() in rotulos_vistos:
            erros.append(f'Faixa {numero}: o rótulo "{faixa["rotulo"]}" está repetido.')
        rotulos_vistos.add(faixa["rotulo"].casefold())
        if len(faixa["descricao"]) > TAMANHO_MAX_DESCRICAO:
            erros.append(
                f"Faixa {numero}: a descrição pode ter até {TAMANHO_MAX_DESCRICAO} caracteres."
            )
        if not COR_VALIDA.match(faixa["cor"]):
            erros.append(f"Faixa {numero}: cor inválida.")

    # 4. Jogadores (um por linha; linhas em branco são ignoradas)
    texto_jogadores = campos.get("jogadores", "")
    nomes = [linha.strip() for linha in texto_jogadores.splitlines() if linha.strip()]
    if not MIN_JOGADORES <= len(nomes) <= MAX_JOGADORES:
        erros.append(f"Informe de {MIN_JOGADORES} a {MAX_JOGADORES} jogadores (um por linha).")
    nomes_vistos = set()
    for nome in nomes:
        if len(nome) > TAMANHO_MAX_NOME_JOGADOR:
            erros.append(f'O nome "{nome[:TAMANHO_MAX_NOME_JOGADOR]}…" passa de '
                         f"{TAMANHO_MAX_NOME_JOGADOR} caracteres.")
        if nome.casefold() in nomes_vistos:
            erros.append(f'O jogador "{nome}" está repetido.')
        nomes_vistos.add(nome.casefold())

    formulario = {
        "modo": modo,
        "tema": nome_tema,
        "rodadas": texto_rodadas,
        "faixas": faixas or FAIXAS_PADRAO,
        "jogadores": texto_jogadores,
    }
    dados = {"tema": tema, "rodadas": rodadas, "faixas": faixas, "jogadores": nomes, "modo": modo}
    return formulario, erros, dados


def criar_partida(tema, rodadas, faixas, jogadores, modo="ao_vivo"):
    """Grava a partida e copia para o banco os itens sorteados do tema.

    Depois disso, editar o temas.json não afeta mais esta partida.
    No modo individual, a partida já nasce aberta (sem "Iniciar") e a ordem
    dos itens de cada jogador é sorteada aqui, uma vez só.
    Devolve o id da partida criada.
    """
    # random.sample sorteia sem repetição e já embaralha a ordem das rodadas.
    sorteados = random.sample(tema["itens"], rodadas)
    estado_inicial = "aberta" if modo == "individual" else "espera"
    con = banco.obter()
    with banco.transacao(con):
        cursor = con.execute(
            "INSERT INTO partidas (tema_nome, modo, estado, total_rodadas, criada_em)"
            " VALUES (?, ?, ?, ?, ?)",
            (tema["nome"], modo, estado_inicial, rodadas, time.time()),
        )
        partida_id = cursor.lastrowid
        con.executemany(
            "INSERT INTO faixas (partida_id, indice, rotulo, descricao, cor) VALUES (?, ?, ?, ?, ?)",
            [(partida_id, indice, f["rotulo"], f["descricao"], f["cor"])
             for indice, f in enumerate(faixas)],
        )
        con.executemany(
            "INSERT INTO itens (partida_id, rodada, nome, imagem) VALUES (?, ?, ?, ?)",
            [(partida_id, rodada, item["nome"], item["imagem"])
             for rodada, item in enumerate(sorteados, start=1)],
        )
        # token_urlsafe(9) gera 12 caracteres aleatórios (72 bits): imprevisível.
        con.executemany(
            "INSERT INTO jogadores (partida_id, nome, codigo) VALUES (?, ?, ?)",
            [(partida_id, nome, secrets.token_urlsafe(9)) for nome in jogadores],
        )
        if modo == "individual":
            individual.sortear_ordens(con, partida_id)
    return partida_id


# ---------------------------------------------------------------------------
# Tela da partida
# ---------------------------------------------------------------------------

@admin.route("/partida/<int:partida_id>")
@exige_admin
def partida(partida_id):
    con = banco.obter()
    dados_partida = con.execute(
        "SELECT * FROM partidas WHERE id = ?", (partida_id,)
    ).fetchone()
    if dados_partida is None:
        abort(404, "Partida não encontrada. Talvez ela tenha sido apagada.")

    faixas = con.execute(
        "SELECT rotulo, descricao, cor FROM faixas WHERE partida_id = ? ORDER BY indice",
        (partida_id,),
    ).fetchall()
    jogadores = con.execute(
        "SELECT nome, codigo FROM jogadores WHERE partida_id = ? ORDER BY id",
        (partida_id,),
    ).fetchall()
    # Modo individual: a confirmação do "Encerrar e revelar" já sai certa na
    # página (sem esperar o primeiro polling), avisando se ninguém finalizou.
    ninguem_finalizou = con.execute(
        "SELECT COUNT(*) FROM jogadores WHERE partida_id = ?"
        " AND removido_em IS NULL AND finalizado_em IS NOT NULL",
        (partida_id,),
    ).fetchone()[0] == 0
    endereco = endereco_publico(
        current_app.config["BASE_URL"], current_app.config["TUNEL_METRICS"]
    )
    return render_template(
        "admin_partida.html",
        partida=dados_partida,
        faixas=faixas,
        jogadores=jogadores,
        endereco=endereco,
        tunel_metrics=current_app.config["TUNEL_METRICS"],
        nomes_estados=jogo.NOMES_DOS_ESTADOS,
        ninguem_finalizou=ninguem_finalizou,
    )


# ---------------------------------------------------------------------------
# Controle da partida e estado ao vivo
# ---------------------------------------------------------------------------

@admin.route("/partida/<int:partida_id>/iniciar", methods=["POST"])
@exige_admin
def iniciar(partida_id):
    con = banco.obter()
    with banco.transacao(con):
        iniciou = jogo.iniciar(con, partida_id)
    if iniciou:
        flash("Partida iniciada!")
    else:
        flash("Nada foi feito: a partida não estava aguardando o início.")
    return redirect(url_for("admin.partida", partida_id=partida_id))


@admin.route("/partida/<int:partida_id>/forcar", methods=["POST"])
@exige_admin
def forcar(partida_id):
    # O formulário manda a fase que o admin estava vendo (ver jogo.forcar_avanco).
    estado_esperado = request.form.get("estado", "")
    try:
        rodada_esperada = int(request.form.get("rodada", ""))
    except ValueError:
        abort(400, "Rodada inválida.")
    con = banco.obter()
    with banco.transacao(con):
        forcou = jogo.forcar_avanco(con, partida_id, estado_esperado, rodada_esperada)
    if forcou:
        flash("Avanço forçado.")
    else:
        flash("Nada foi feito: a partida já tinha mudado de fase.")
    return redirect(url_for("admin.partida", partida_id=partida_id))


@admin.route("/partida/<int:partida_id>/encerrar", methods=["POST"])
@exige_admin
def encerrar(partida_id):
    # "Encerrar e revelar" do modo individual.
    con = banco.obter()
    with banco.transacao(con):
        encerrou = individual.encerrar(con, partida_id)
    if encerrou:
        flash("Partida encerrada: os resultados foram revelados.")
    else:
        flash("Nada foi feito: a partida não estava aberta no modo individual.")
    return redirect(url_for("admin.partida", partida_id=partida_id))


@admin.route("/partida/<int:partida_id>/remover/<int:jogador_id>", methods=["POST"])
@exige_admin
def remover(partida_id, jogador_id):
    # O jogador tem de ser DESTA partida (jogo.remover_jogador confere): o id de
    # jogador pode ser reaproveitado depois de apagar uma partida, o de partida não.
    con = banco.obter()
    try:
        with banco.transacao(con):
            removeu = jogo.remover_jogador(con, partida_id, jogador_id, time.time())
        flash("Jogador removido." if removeu else "Esse jogador já tinha sido removido.")
    except jogo.AcaoInvalida as problema:
        flash(f"Nada foi feito: {problema}")
    return redirect(url_for("admin.partida", partida_id=partida_id))


@admin.route("/api/estado/<int:partida_id>")
def api_estado(partida_id):
    # Rota de API: sem login devolve JSON 401 em vez de redirecionar.
    if not session.get("admin"):
        return jsonify({"erro": "Faça login de novo."}), 401
    con = banco.obter()
    with banco.transacao(con):
        agora = time.time()  # lido DEPOIS de pegar a trava (ver rotas_jogador.executar_acao)
        jogo.verificar_avanco(con, partida_id, agora)
        existe = con.execute("SELECT 1 FROM partidas WHERE id = ?", (partida_id,)).fetchone()
        dados = jogo.montar_estado(con, partida_id, agora, para_admin=True) if existe else None
    if dados is None:
        resposta = jsonify({"apagada": True})
        resposta.status_code = 404
    else:
        resposta = jsonify(dados)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta

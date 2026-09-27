"""Leitura e validação do arquivo de temas (temas.json).

O arquivo é lido de novo toda vez que o admin abre a tela de nova partida,
então dá para editar os temas sem reiniciar o app.
"""
import hashlib
import json
from collections import Counter


def _texto(valor):
    """Devolve o valor sem espaços nas pontas se for texto; senão, ''."""
    return valor.strip() if isinstance(valor, str) else ""


def carregar(caminho):
    """Lê e valida o arquivo de temas.

    Devolve (temas, erro):
    - erro: texto explicando por que o arquivo inteiro não pôde ser usado, ou None;
    - temas: lista de dicionários com as chaves
      "nome", "itens" (lista de {"nome", "imagem"}), "valido", "motivos"
      e "assinatura".
    """
    try:
        # utf-8-sig aceita arquivos salvos com BOM (comum no Bloco de Notas).
        with open(caminho, encoding="utf-8-sig") as arquivo:
            texto = arquivo.read()
    except FileNotFoundError:
        return [], f"Arquivo de temas não encontrado: {caminho}"
    except UnicodeDecodeError:
        return [], "O arquivo de temas não está em UTF-8."
    except OSError as erro:
        return [], f"Não consegui ler o arquivo de temas: {erro}"

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        return [], f"JSON inválido na linha {erro.lineno}, coluna {erro.colno}: {erro.msg}"

    if not isinstance(dados, dict) or not isinstance(dados.get("temas"), list):
        return [], 'O arquivo precisa ter o formato {"temas": [ ... ]}.'

    temas = [_validar_tema(bruto) for bruto in dados["temas"]]

    # Nome de tema repetido: todos os temas com esse nome ficam inválidos,
    # porque a tela de nova partida escolhe o tema pelo nome.
    contagem = Counter(tema["nome"].casefold() for tema in temas if tema["nome"])
    for tema in temas:
        if tema["nome"] and contagem[tema["nome"].casefold()] > 1:
            tema["motivos"].append("nome de tema repetido no arquivo")

    for tema in temas:
        tema["valido"] = not tema["motivos"]
        tema["assinatura"] = assinatura(tema)
    return temas, None


def assinatura(tema):
    """Resumo curto do conteúdo do tema (nome + itens).

    A tela de nova partida envia a assinatura do tema que estava na prévia.
    Se o temas.json mudou nesse meio-tempo, a assinatura muda e a criação é
    recusada, para a partida nunca ter itens diferentes dos que o admin viu.
    """
    conteudo = json.dumps(
        {"nome": tema["nome"], "itens": tema["itens"]}, ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]


def _validar_tema(bruto):
    """Confere um tema e devolve {"nome", "itens", "motivos"}."""
    if not isinstance(bruto, dict):
        return {"nome": "", "itens": [], "motivos": ["o tema não é um objeto { }"]}

    motivos = []
    nome = _texto(bruto.get("nome"))
    if not nome:
        motivos.append("nome do tema vazio")

    itens_brutos = bruto.get("itens")
    if not isinstance(itens_brutos, list):
        motivos.append('"itens" precisa ser uma lista')
        itens_brutos = []
    elif len(itens_brutos) < 2:
        motivos.append("precisa de pelo menos 2 itens")

    itens = []
    nomes_vistos = set()
    for numero, item in enumerate(itens_brutos, start=1):
        if not isinstance(item, dict):
            motivos.append(f"item {numero}: não é um objeto {{ }}")
            continue
        nome_item = _texto(item.get("nome"))
        imagem = _texto(item.get("imagem"))
        if not nome_item:
            motivos.append(f"item {numero}: nome vazio")
        elif nome_item.casefold() in nomes_vistos:
            motivos.append(f'item {numero}: nome "{nome_item}" repetido')
        nomes_vistos.add(nome_item.casefold())
        if not imagem.startswith(("https://", "http://")):
            motivos.append(f"item {numero}: a imagem precisa começar com https:// ou http://")
        itens.append({"nome": nome_item, "imagem": imagem})

    return {"nome": nome, "itens": itens, "motivos": motivos}

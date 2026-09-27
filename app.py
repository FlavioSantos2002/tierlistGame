"""Ponto de entrada do app Tier List em grupo.

No celular: gunicorn -w 1 --threads 4 -b 127.0.0.1:5001 app:app
No PC:      python app.py
"""
import os
import time

from flask import Flask, redirect, render_template, url_for
from werkzeug.exceptions import HTTPException

import banco
from jogo import NOMES_DOS_ESTADOS
from rotas_admin import admin
from rotas_jogador import jogador

# Valores que aparecem no .env.example. Se o .env ainda estiver com eles,
# o app se recusa a subir (senha e chave conhecidas por qualquer um).
VALORES_DE_EXEMPLO = {
    "ADMIN_TOKEN": "troque-este-token",
    "SECRET_KEY": "troque-esta-chave",
}

MENSAGENS_DE_ERRO = {
    400: "Requisição inválida.",
    404: "Página não encontrada.",
    405: "Método não permitido.",
    413: "Dados grandes demais.",
}


def variavel_obrigatoria(nome):
    """Lê uma variável de ambiente que não pode ficar vazia nem com o valor de exemplo."""
    valor = os.environ.get(nome, "").strip()
    if not valor:
        raise RuntimeError(f"A variável de ambiente {nome} está vazia. Preencha no .env.")
    if valor == VALORES_DE_EXEMPLO[nome]:
        raise RuntimeError(
            f"A variável de ambiente {nome} ainda está com o valor de exemplo. Troque no .env."
        )
    return valor


def criar_app():
    app = Flask(__name__)
    app.config.update(
        ADMIN_TOKEN=variavel_obrigatoria("ADMIN_TOKEN"),
        SECRET_KEY=variavel_obrigatoria("SECRET_KEY"),
        DB_PATH=os.environ.get("DB_PATH", "").strip() or "./tierlist.db",
        TEMAS_PATH=os.environ.get("TEMAS_PATH", "").strip() or "./temas.json",
        TUNEL_METRICS=os.environ.get("TUNEL_METRICS", "").strip() or "127.0.0.1:2001",
        BASE_URL=os.environ.get("BASE_URL", "").strip(),
        # Cookie da sessão: inacessível ao JavaScript e não enviado em POST de outros sites.
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Só vai por HTTPS. No celular todo acesso passa pelo túnel (HTTPS), e o
        # gunicorn só escuta em 127.0.0.1. O servidor de desenvolvimento do PC
        # (HTTP) desliga isto lá embaixo, no "if __name__".
        SESSION_COOKIE_SECURE=True,
        # Nenhum formulário ou JSON do app chega perto disso.
        MAX_CONTENT_LENGTH=64 * 1024,
    )

    banco.criar_tabelas(app.config["DB_PATH"])
    app.teardown_appcontext(banco.fechar)

    app.register_blueprint(admin)
    app.register_blueprint(jogador)

    @app.route("/")
    def inicio():
        return redirect(url_for("admin.lista"))

    @app.template_filter("data")
    def formatar_data(horario_unix):
        """Mostra um horário Unix como 25/09/2026 14:30 (fuso do sistema)."""
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(horario_unix))

    @app.template_filter("nome_estado")
    def nome_estado(estado):
        return NOMES_DOS_ESTADOS.get(estado, estado)

    @app.template_filter("cor_do_texto")
    def cor_do_texto(cor):
        """Preto ou branco, o que contrastar mais com a cor de fundo (#rrggbb).
        É a mesma conta do corDoTexto() em static/comum.js."""
        r, g, b = int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)
        return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"

    @app.errorhandler(HTTPException)
    def pagina_de_erro(erro):
        # Se o código chamou abort(404, "mensagem"), mostramos a mensagem;
        # senão, um texto padrão em português.
        if erro.description != type(erro).description:
            mensagem = erro.description
        else:
            mensagem = MENSAGENS_DE_ERRO.get(erro.code, "Algo deu errado.")
        return render_template("erro.html", codigo=erro.code, mensagem=mensagem), erro.code

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        return resposta

    return app


app = criar_app()

if __name__ == "__main__":
    # Servidor de desenvolvimento (só no PC). No celular use o gunicorn.
    # Aqui o acesso é por HTTP, então o cookie não pode exigir HTTPS.
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(host="127.0.0.1", port=5001, debug=True)

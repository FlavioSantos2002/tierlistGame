#!/data/data/com.termux/files/usr/bin/bash
# Sobe o Tier List no Termux (celular), em duas sessões tmux:
#   tl-app    gunicorn na porta 5001
#   tl-tunel  cloudflared (quick tunnel), métricas em TUNEL_METRICS (padrão 127.0.0.1:2001)
# Mexe SÓ nessas duas sessões: as do convite (porta 5000, métricas 2000) continuam rodando.
#
# Uso:  cd ~/tierlist && bash iniciar.sh
set -eu

PASTA="$(cd "$(dirname "$0")" && pwd -P)"
cd "$PASTA"

SESSAO_APP="tl-app"
SESSAO_TUNEL="tl-tunel"
PORTA_APP=5001

erro() {
  echo "ERRO: $*" >&2
  exit 1
}

# ----- Conferências antes de mexer em qualquer coisa -----

for programa in tmux cloudflared gunicorn python termux-wake-lock; do
  command -v "$programa" >/dev/null 2>&1 \
    || erro "não achei '$programa'. Veja a 'Primeira instalação' no README."
done

[ -f .env ] || erro "falta o arquivo .env. Crie a partir do .env.example (veja o README)."
# Arquivo salvo no Windows (CRLF) quebra o .env e o Python: lição já aprendida.
# (Lê os bytes com Python: alguns grep escondem o \r ao abrir em modo texto.)
for arquivo in .env *.py *.sh; do
  if python -c "import sys; sys.exit(b'\r' not in open(sys.argv[1], 'rb').read())" "$arquivo"; then
    erro "$arquivo com final de linha do Windows (CRLF). Corrija com:  sed -i 's/\r\$//' $arquivo"
  fi
done

# Carrega o .env aqui só para ler TUNEL_METRICS, BASE_URL e TZ.
set -a
. ./.env
set +a
TUNEL_METRICS="${TUNEL_METRICS:-127.0.0.1:2001}"
BASE_URL="${BASE_URL:-}"

# Fuso para as datas do painel: o do .env (TZ) ou o do Android.
FUSO="${TZ:-$(getprop persist.sys.timezone 2>/dev/null || true)}"

# O que cada sessão roda antes do programa: entrar na pasta e carregar o .env
# DE NOVO. Se o servidor tmux já estiver rodando (por causa do convite), uma
# sessão nova NÃO recebe as variáveis exportadas por este script.
PREPARO="cd '$PASTA' && set -a && . ./.env && set +a"
if [ -n "$FUSO" ]; then
  PREPARO="$PREPARO && export TZ='$FUSO'"
fi
# Se o programa parar, a sessão continua aberta mostrando o erro
# (para ver: tmux attach -t tl-app).
DEPOIS="echo; echo 'Parou. Veja a mensagem acima. (Sair: Ctrl+B e depois D)'; exec bash"

# Pergunta a uma URL local; sucesso se ela responder 200.
responde() {
  python - "$1" <<'FIM'
import sys, urllib.request
abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with abridor.open(sys.argv[1], timeout=2) as resposta:
        sys.exit(0 if resposta.status == 200 else 1)
except Exception:
    sys.exit(1)
FIM
}

# Endereço público atual do quick tunnel ("" se o túnel ainda não subiu).
endereco_do_tunel() {
  python - "http://$TUNEL_METRICS/quicktunnel" <<'FIM'
import json, sys, urllib.request
abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with abridor.open(sys.argv[1], timeout=2) as resposta:
        host = (json.load(resposta).get("hostname") or "").strip().rstrip("/")
except Exception:
    host = ""
if host and not host.startswith(("https://", "http://")):
    host = "https://" + host
print(host)
FIM
}

# ----- Reinício limpo: só as sessões deste projeto -----

termux-wake-lock
# Para o app e o túnel antigos de verdade (SIGTERM + espera; ver parar.sh).
bash "$PASTA/parar.sh"
# Se ainda houver algo respondendo na porta, o app novo não conseguiria subir
# e o antigo esconderia o problema.
if responde "http://127.0.0.1:$PORTA_APP/admin/entrar"; then
  erro "a porta $PORTA_APP continua respondendo depois de parar. Veja com: tmux ls"
fi

echo "Subindo o app (sessão $SESSAO_APP, porta $PORTA_APP)..."
tmux new-session -d -s "$SESSAO_APP" \
  "$PREPARO && gunicorn -w 1 --threads 4 -b 127.0.0.1:$PORTA_APP --pid gunicorn.pid app:app; $DEPOIS"

echo "Subindo o túnel (sessão $SESSAO_TUNEL, métricas em $TUNEL_METRICS)..."
tmux new-session -d -s "$SESSAO_TUNEL" \
  "$PREPARO && cloudflared tunnel --no-autoupdate --pidfile cloudflared.pid --metrics $TUNEL_METRICS --url http://localhost:$PORTA_APP; $DEPOIS"

# ----- Espera os dois ficarem prontos -----

echo "Esperando o app responder..."
app_ok=0
for _ in $(seq 1 30); do
  if responde "http://127.0.0.1:$PORTA_APP/admin/entrar"; then app_ok=1; break; fi
  sleep 1
done
[ "$app_ok" = 1 ] || erro "o app não respondeu em 30 s. Veja o motivo com:  tmux attach -t $SESSAO_APP"

echo "Esperando o túnel informar o endereço público..."
endereco=""
for _ in $(seq 1 60); do
  endereco="$(endereco_do_tunel)"
  [ -n "$endereco" ] && break
  sleep 1
done
[ -n "$endereco" ] || erro "o túnel não informou o endereço em 60 s. Veja o motivo com:  tmux attach -t $SESSAO_TUNEL"

echo
echo "Tier List no ar!"
echo "  Endereço público: $endereco"
echo "  Painel do admin:  $endereco/admin"
if [ -n "$BASE_URL" ]; then
  echo "  Obs.: BASE_URL está preenchida ($BASE_URL); os links dos jogadores usam ela."
fi
echo
echo "O endereço do quick tunnel muda a cada reinício. Links enviados antes deste"
echo "reinício pararam de funcionar: copie os novos na tela da partida."

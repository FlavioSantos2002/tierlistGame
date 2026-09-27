#!/data/data/com.termux/files/usr/bin/bash
# Para o Tier List (app e túnel) com segurança. Mexe SÓ neste projeto:
# as sessões e processos do convite continuam rodando.
#
# Uso:  cd ~/tierlist && bash parar.sh
#
# Por que não basta "tmux kill-session": fechar a sessão manda SIGHUP, e o
# gunicorn trata SIGHUP como "recarregar", não como "sair". Ele poderia
# continuar rodando sem sessão, segurando a porta 5001 e o banco aberto.
# Aqui mandamos SIGTERM (sair) e esperamos o processo terminar de verdade.
set -eu

PASTA="$(cd "$(dirname "$0")" && pwd -P)"
cd "$PASTA"

# Encerra o processo cujo PID está no arquivo e espera ele sair.
encerrar() {
  local nome="$1" arquivo="$2" pid
  [ -f "$arquivo" ] || return 0
  pid="$(cat "$arquivo")"
  # Só mexe no processo se ele ainda existir E estiver rodando nesta pasta.
  # (Um arquivo de PID velho pode apontar para um número que o Android deu
  # a outro processo, por exemplo do convite: esse nunca é morto.)
  if kill -0 "$pid" 2>/dev/null && [ "$(readlink "/proc/$pid/cwd" 2>/dev/null)" = "$PASTA" ]; then
    echo "Parando $nome (PID $pid)..."
    kill -TERM "$pid"
    for _ in $(seq 1 40); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "ERRO: $nome (PID $pid) não parou em 20 s. Veja com: tmux attach -t tl-app" >&2
      exit 1
    fi
  fi
  rm -f "$arquivo"
}

encerrar "o app" gunicorn.pid
encerrar "o túnel" cloudflared.pid

# Agora sim fecha as sessões ("=nome" pede o nome EXATO).
tmux kill-session -t "=tl-app" 2>/dev/null || true
tmux kill-session -t "=tl-tunel" 2>/dev/null || true
echo "Tier List parado."

"""Descobre o endereço público do app (usado para montar os links dos jogadores).

Ordem de prioridade:
1. BASE_URL, se estiver preenchida;
2. o endereço atual do quick tunnel, lido em http://<TUNEL_METRICS>/quicktunnel;
3. se nada funcionar, devolve None e o painel mostra um aviso
   (nunca geramos links com "localhost").
"""
import json
import threading
import time
import urllib.request

CACHE_SEGUNDOS = 30
TIMEOUT_SEGUNDOS = 1

_cache = {"endereco": None, "quando": 0.0}
_trava = threading.Lock()

# Abridor de URLs que ignora proxies configurados no sistema:
# as métricas do túnel estão sempre na própria máquina.
_abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def endereco_publico(base_url, tunel_metrics):
    """Devolve algo como "https://exemplo.trycloudflare.com" (sem "/" no fim) ou None."""
    if base_url:
        return base_url.rstrip("/")

    with _trava:
        agora = time.monotonic()
        # Só guardamos em cache quando deu certo: se o túnel ainda está
        # subindo, a próxima abertura da página tenta de novo.
        if _cache["endereco"] and agora - _cache["quando"] < CACHE_SEGUNDOS:
            return _cache["endereco"]

        endereco = _consultar_tunel(tunel_metrics)
        if endereco:
            _cache["endereco"] = endereco
            _cache["quando"] = agora
        return endereco


def _consultar_tunel(tunel_metrics):
    """Pergunta ao cloudflared qual é o hostname atual do quick tunnel."""
    url = f"http://{tunel_metrics}/quicktunnel"
    try:
        with _abridor.open(url, timeout=TIMEOUT_SEGUNDOS) as resposta:
            dados = json.load(resposta)
    except (OSError, ValueError):
        # OSError cobre conexão recusada e timeout; ValueError cobre JSON inválido.
        return None

    hostname = dados.get("hostname") if isinstance(dados, dict) else None
    if not isinstance(hostname, str) or not hostname.strip():
        return None
    hostname = hostname.strip().rstrip("/")
    if hostname.startswith(("https://", "http://")):
        return hostname
    return f"https://{hostname}"

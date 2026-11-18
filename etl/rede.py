"""Download de JSON com novas tentativas (somente biblioteca padrão)."""
import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

AGENTE = "MenteAcessivel-SP/1.0 (projeto academico)"


def decodificar(bruto, codificacao=""):
    """Descompacta (gzip/deflate) se preciso e converte para texto."""
    codificacao = (codificacao or "").lower()
    if bruto[:2] == b"\x1f\x8b" or "gzip" in codificacao:
        bruto = gzip.decompress(bruto)
    elif "deflate" in codificacao:
        try:
            bruto = zlib.decompress(bruto)
        except zlib.error:
            bruto = zlib.decompress(bruto, -zlib.MAX_WBITS)
    for charset in ("utf-8-sig", "latin-1"):
        try:
            return bruto.decode(charset)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", errors="replace")


def baixar_json(url, parametros=None, tentativas=4, espera=2.0, timeout=60):
    if parametros:
        url = f"{url}?{urllib.parse.urlencode(parametros, safe='[]')}"
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            pedido = urllib.request.Request(url, headers={
                "User-Agent": AGENTE,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            })
            with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
                bruto = resposta.read()
                codificacao = resposta.headers.get("Content-Encoding", "")
            return json.loads(decodificar(bruto, codificacao))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError,
                OSError, EOFError, zlib.error) as erro:
            ultimo_erro = erro
            if isinstance(erro, urllib.error.HTTPError) and erro.code in (400, 401, 403, 404):
                break
            time.sleep(espera * tentativa)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")

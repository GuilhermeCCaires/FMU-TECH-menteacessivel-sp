"""Rotas até a unidade: carro e a pé (OSRM/FOSSGIS) e links para transporte público.

Carro e a pé: servidor OSRM comunitário do OpenStreetMap, mantido pela FOSSGIS
(https://routing.openstreetmap.de). Gratuito, sem chave, mas sem garantia e com
política de uso que proíbe uso pesado: por isso há cache e a rota só é pedida
quando a pessoa toca em "Como chegar".

Transporte público: não existe serviço gratuito sem chave que calcule rotas de
ônibus/metrô/trem em SP, então o app abre o Google Maps ou o Moovit já com a
rota de transporte público.
"""
import threading
import urllib.parse
from collections import OrderedDict

from . import geo

URL_OSRM = "https://routing.openstreetmap.de/{perfil}/route/v1/driving/{o_lon},{o_lat};{d_lon},{d_lat}"
PERFIS = {"carro": "routed-car", "a_pe": "routed-foot"}
MODOS = ("transporte", "carro", "a_pe")
DISTANCIA_MAX_KM = 150  # rotas maiores: melhor abrir direto no Google Maps

_cache = OrderedDict()
_trava = threading.Lock()
TAMANHO_CACHE = 500


class ErroRota(Exception):
    pass


# --------------------------------------------------------------- instruções
DIRECAO = {
    "uturn": "faça o retorno", "sharp right": "vire acentuadamente à direita",
    "right": "vire à direita", "slight right": "mantenha-se à direita",
    "straight": "siga em frente", "slight left": "mantenha-se à esquerda",
    "left": "vire à esquerda", "sharp left": "vire acentuadamente à esquerda",
}
LADO = {"right": "direita", "slight right": "direita", "sharp right": "direita",
        "left": "esquerda", "slight left": "esquerda", "sharp left": "esquerda"}


def _via(nome):
    return nome if nome else "a via sem nome"


def _na(nome):
    return f"na {nome}" if nome else "na via sem nome"


def instrucao(passo, destino="o destino"):
    """Converte um passo do OSRM em uma frase em português."""
    manobra = passo.get("maneuver", {})
    tipo = manobra.get("type", "")
    mod = manobra.get("modifier", "")
    nome = (passo.get("name") or "").strip()
    ref = (passo.get("ref") or "").strip()
    if ref and ref not in nome:
        nome = f"{nome} ({ref})" if nome else ref

    if tipo == "depart":
        return f"Comece pela {_via(nome)}"
    if tipo == "arrive":
        lado = LADO.get(mod)
        return f"Chegada: {destino}" + (f", à {lado}" if lado else "")
    if tipo in ("roundabout", "rotary", "roundabout turn"):
        saida = manobra.get("exit")
        if saida:
            return f"Na rotatória, pegue a {saida}ª saída para {_via(nome)}"
        return f"Na rotatória, siga para {_via(nome)}"
    if tipo in ("exit roundabout", "exit rotary"):
        return f"Saia da rotatória para {_via(nome)}"
    if tipo == "fork":
        return f"Na bifurcação, mantenha-se à {LADO.get(mod, 'direita')} para {_via(nome)}"
    if tipo == "end of road":
        return f"No fim da via, vire à {LADO.get(mod, 'direita')} {_na(nome)}"
    if tipo == "merge":
        return f"Entre {_na(nome)}"
    if tipo == "on ramp":
        return f"Pegue o acesso para {_via(nome)}"
    if tipo == "off ramp":
        return f"Pegue a saída para {_via(nome)}"
    if tipo in ("continue", "new name", "notification"):
        if mod in ("left", "right", "sharp left", "sharp right", "uturn"):
            return f"{DIRECAO[mod].capitalize()} {_na(nome)}"
        return f"Continue pela {_via(nome)}"
    # turn e demais
    acao = DIRECAO.get(mod, "siga")
    return f"{acao.capitalize()} {_na(nome)}"


# -------------------------------------------------------------- montar rota
def montar_rota(resposta, modo, nome_destino):
    if not isinstance(resposta, dict) or resposta.get("code") != "Ok" or not resposta.get("routes"):
        raise ErroRota(f"Servidor de rotas respondeu: {resposta.get('code') if isinstance(resposta, dict) else '?'}")
    rota = resposta["routes"][0]
    passos = []
    for perna in rota.get("legs", []):
        for passo in perna.get("steps", []):
            texto = instrucao(passo, nome_destino)
            distancia = round(passo.get("distance", 0))
            # Junta passos repetidos ("Continue pela X" seguido de "Continue pela X")
            if passos and passos[-1]["instrucao"] == texto:
                passos[-1]["distancia_m"] += distancia
                continue
            passos.append({"instrucao": texto, "distancia_m": distancia})
    return {
        "modo": modo,
        "distancia_m": round(rota.get("distance", 0)),
        "duracao_s": round(rota.get("duration", 0)),
        "geometria": (rota.get("geometry") or {}).get("coordinates", []),  # [lon, lat]
        "passos": passos,
        "fonte": "OpenStreetMap / OSRM (routing.openstreetmap.de, FOSSGIS)",
    }


def _chave(modo, origem, destino):
    return (modo, round(origem[0], 4), round(origem[1], 4), round(destino[0], 4), round(destino[1], 4))


def calcular(modo, origem, destino, nome_destino="o destino", baixar=None):
    """origem/destino = (lat, lon). Retorna a rota pronta para o app."""
    if modo not in PERFIS:
        raise ErroRota("Modo de rota inválido")
    if geo.haversine_km(*origem, *destino) > DISTANCIA_MAX_KM:
        raise ErroRota("Distância muito grande para calcular aqui; use o Google Maps.")
    chave = _chave(modo, origem, destino)
    with _trava:
        if chave in _cache:
            _cache.move_to_end(chave)
            return _cache[chave]
    if baixar is None:
        from etl.rede import baixar_json as baixar
    url = URL_OSRM.format(perfil=PERFIS[modo], o_lat=origem[0], o_lon=origem[1],
                          d_lat=destino[0], d_lon=destino[1])
    try:
        resposta = baixar(url, {"overview": "full", "geometries": "geojson", "steps": "true"},
                          tentativas=2, espera=1.0, timeout=15)
    except RuntimeError as erro:
        raise ErroRota("Servidor de rotas indisponível no momento") from erro
    rota = montar_rota(resposta, modo, nome_destino)
    with _trava:
        _cache[chave] = rota
        while len(_cache) > TAMANHO_CACHE:
            _cache.popitem(last=False)
    return rota


# ------------------------------------------------------- links externos
def links_externos(origem, destino, nome_destino):
    """Links para abrir a rota em outros apps, por modo."""
    o = f"{origem[0]},{origem[1]}" if origem else None
    d = f"{destino[0]},{destino[1]}"

    def google(modo):
        params = {"api": 1, "destination": d, "travelmode": modo}
        if o:
            params["origin"] = o
        return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)

    moovit = "https://moovit.com/?" + urllib.parse.urlencode(
        {"to": nome_destino, "tll": f"{destino[0]}_{destino[1]}", "lang": "pt"})
    waze = "https://waze.com/ul?" + urllib.parse.urlencode(
        {"ll": d, "navigate": "yes", "utm_source": "menteacessivel"})
    return {
        "transporte": [{"nome": "Google Maps (ônibus, metrô e trem)", "url": google("transit")},
                       {"nome": "Moovit", "url": moovit}],
        "carro": [{"nome": "Google Maps", "url": google("driving")},
                  {"nome": "Waze", "url": waze}],
        "a_pe": [{"nome": "Google Maps", "url": google("walking")}],
    }

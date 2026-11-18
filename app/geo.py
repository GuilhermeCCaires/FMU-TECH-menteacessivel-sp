"""Funções geográficas: distância de Haversine, conversões e ponto-em-polígono."""
import math

RAIO_TERRA_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Distância em linha reta sobre a superfície da Terra (km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(min(1.0, math.sqrt(a)))


def para_vetor(lat, lon):
    """Converte lat/lon em vetor 3D na esfera unitária.

    A distância euclidiana (corda) entre dois vetores cresce junto com a
    distância de Haversine, então uma KD-tree euclidiana em 3D encontra
    exatamente os vizinhos mais próximos sobre a esfera.
    """
    p, l = math.radians(lat), math.radians(lon)
    return (math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p))


def km_para_corda(km):
    return 2 * math.sin(min(km, math.pi * RAIO_TERRA_KM) / (2 * RAIO_TERRA_KM))


def corda_para_km(corda):
    return 2 * RAIO_TERRA_KM * math.asin(min(1.0, corda / 2))


# ---------------------------------------------------------------------------
# Polígonos (GeoJSON: coordenadas em [lon, lat])
# ---------------------------------------------------------------------------

def _ponto_no_anel(lon, lat, anel):
    """Ray casting: conta quantas arestas um raio horizontal cruza."""
    dentro = False
    n = len(anel)
    j = n - 1
    for i in range(n):
        xi, yi = anel[i][0], anel[i][1]
        xj, yj = anel[j][0], anel[j][1]
        if (yi > lat) != (yj > lat):
            x_cruz = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cruz:
                dentro = not dentro
        j = i
    return dentro


def _ponto_no_poligono(lon, lat, poligono):
    """poligono = [anel_externo, buraco1, ...]"""
    if not poligono or not _ponto_no_anel(lon, lat, poligono[0]):
        return False
    return not any(_ponto_no_anel(lon, lat, buraco) for buraco in poligono[1:])


def poligonos_da_geometria(geometria):
    tipo = geometria.get("type")
    coords = geometria.get("coordinates") or []
    if tipo == "Polygon":
        return [coords]
    if tipo == "MultiPolygon":
        return list(coords)
    return []


def caixa_envolvente(geometria):
    lons, lats = [], []
    for poligono in poligonos_da_geometria(geometria):
        for lon, lat, *_ in poligono[0]:
            lons.append(lon)
            lats.append(lat)
    if not lons:
        return None
    return (min(lons), min(lats), max(lons), max(lats))


def ponto_na_geometria(lat, lon, geometria, caixa=None):
    if caixa:
        minx, miny, maxx, maxy = caixa
        if not (minx <= lon <= maxx and miny <= lat <= maxy):
            return False
    return any(_ponto_no_poligono(lon, lat, p) for p in poligonos_da_geometria(geometria))


def _area_e_centroide_anel(anel):
    """Fórmula do polígono (shoelace) para área e centroide planos."""
    a = cx = cy = 0.0
    n = len(anel)
    for i in range(n - 1):
        x0, y0 = anel[i][0], anel[i][1]
        x1, y1 = anel[i + 1][0], anel[i + 1][1]
        cruz = x0 * y1 - x1 * y0
        a += cruz
        cx += (x0 + x1) * cruz
        cy += (y0 + y1) * cruz
    a /= 2
    if abs(a) < 1e-12:
        xs = [p[0] for p in anel]
        ys = [p[1] for p in anel]
        return 0.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    return a, (cx / (6 * a), cy / (6 * a))


def centroide(geometria):
    """Centroide (lat, lon) do maior polígono da geometria."""
    melhor = None
    for poligono in poligonos_da_geometria(geometria):
        area, (x, y) = _area_e_centroide_anel(poligono[0])
        if melhor is None or abs(area) > melhor[0]:
            melhor = (abs(area), (y, x))
    return melhor[1] if melhor else None

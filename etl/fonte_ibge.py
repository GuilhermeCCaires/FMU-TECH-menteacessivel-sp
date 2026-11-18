"""Coleta de dados do IBGE: municípios, população (Censo 2022) e malha territorial."""
from .rede import baixar_json

BASE = "https://servicodados.ibge.gov.br/api"


def municipios(uf=35):
    dados = baixar_json(f"{BASE}/v1/localidades/estados/{uf}/municipios")
    saida = []
    for m in dados:
        imediata = m.get("regiao-imediata") or {}
        intermediaria = imediata.get("regiao-intermediaria") or {}
        if not imediata and m.get("microrregiao"):  # formato antigo da API
            imediata = m["microrregiao"]
            intermediaria = imediata.get("mesorregiao") or {}
        saida.append({
            "codigo_ibge": int(m["id"]),
            "nome": m["nome"],
            "regiao_imediata": imediata.get("nome"),
            "regiao_intermediaria": intermediaria.get("nome"),
        })
    return saida


def _serie_por_municipio(resposta):
    valores = {}
    for variavel in resposta or []:
        for resultado in variavel.get("resultados", []):
            for serie in resultado.get("series", []):
                cod = int(serie["localidade"]["id"])
                valor = list(serie["serie"].values())[-1]
                try:
                    valores[cod] = int(float(valor))
                except (TypeError, ValueError):
                    continue
    return valores


def populacao(uf=35, log=print):
    """População residente do Censo 2022 (agregado 4709, variável 93).

    Se a consulta falhar, usa a estimativa mais recente (agregado 6579, variável 9324).
    """
    localidades = {"localidades": f"N6[N3[{uf}]]"}
    try:
        resposta = baixar_json(f"{BASE}/v3/agregados/4709/periodos/2022/variaveis/93", localidades)
        valores = _serie_por_municipio(resposta)
        if valores:
            return valores, "IBGE - Censo Demográfico 2022 (tabela 4709)"
    except RuntimeError as erro:
        log(f"  IBGE: Censo 2022 indisponível ({erro}); usando estimativa.")
    resposta = baixar_json(f"{BASE}/v3/agregados/6579/periodos/-1/variaveis/9324", localidades)
    return _serie_por_municipio(resposta), "IBGE - Estimativa populacional (tabela 6579)"


def malha(uf=35):
    """GeoJSON com os polígonos dos municípios (qualidade mínima, leve para a web)."""
    return baixar_json(f"{BASE}/v3/malhas/estados/{uf}", {
        "formato": "application/vnd.geo+json",
        "qualidade": "minima",
        "intrarregiao": "municipio",
    }, timeout=120)

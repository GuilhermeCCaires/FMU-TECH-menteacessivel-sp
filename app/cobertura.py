"""Indicadores de cobertura e déficit de CAPS.

Indicador oficial (Ministério da Saúde), CAPS por 100 mil habitantes ponderado:
  (0,5 x CAPS I + CAPS II + CAPSi + CAPS AD + 1,5 x (CAPS III + CAPS AD III)) / pop x 100.000

Faixas: > 0,70 muito boa | 0,50-0,69 boa | 0,35-0,49 regular/baixa |
        0,20-0,34 baixa | < 0,20 insuficiente/crítica

Parâmetros populacionais de implantação: > 15 mil hab. CAPS I; > 70 mil hab.
CAPS II, CAPS AD e CAPSi; > 150 mil hab. CAPS III e CAPS AD III.
"""
from collections import Counter, defaultdict

from .classificacao import PESO_COBERTURA

FAIXAS = ["Muito boa", "Boa", "Regular/baixa", "Baixa", "Insuficiente/crítica"]


def classificar_cobertura(indice):
    if indice is None:
        return "Sem dados"
    if indice > 0.70:
        return "Muito boa"
    if indice >= 0.50:
        return "Boa"
    if indice >= 0.35:
        return "Regular/baixa"
    if indice >= 0.20:
        return "Baixa"
    return "Insuficiente/crítica"


def indice_cobertura(contagem, populacao):
    if not populacao:
        return None
    ponderado = sum(PESO_COBERTURA.get(mod, 0) * n for mod, n in contagem.items())
    return ponderado / populacao * 100_000


def deficit_por_parametro(contagem, populacao):
    """Lista as modalidades que o porte do município indica e que não existem nele."""
    if not populacao:
        return []
    faltam = []
    gerais = sum(contagem.get(m, 0) for m in ("CAPS_I", "CAPS_II", "CAPS_III", "CAPS_NI"))
    ad = sum(contagem.get(m, 0) for m in ("CAPS_AD", "CAPS_AD_III", "CAPS_AD_IV"))
    ad_24h = contagem.get("CAPS_AD_III", 0) + contagem.get("CAPS_AD_IV", 0)
    if populacao > 15_000 and gerais == 0:
        faltam.append("CAPS I ou II")
    if populacao > 70_000:
        if ad == 0:
            faltam.append("CAPS AD")
        if contagem.get("CAPS_IJ", 0) == 0:
            faltam.append("CAPS Infantojuvenil")
    if populacao > 150_000:
        if contagem.get("CAPS_III", 0) == 0:
            faltam.append("CAPS III (24h)")
        if ad_24h == 0:
            faltam.append("CAPS AD III (24h)")
    return faltam


def calcular(unidades, municipios, eventos=None):
    """Retorna indicadores por município, por região imediata e do estado."""
    caps_por_mun = defaultdict(Counter)
    for u in unidades:
        if u["categoria"] == "CAPS":
            caps_por_mun[u["municipio_ibge"]][u["modalidade"]] += 1

    demanda = defaultdict(lambda: {"buscas": 0, "sem_resultado_perto": 0})
    for e in eventos or []:
        d = demanda[e["municipio_ibge"]]
        d["buscas"] += 1
        if not e["resultados"] or (e["distancia_primeiro_km"] or 0) > 30:
            d["sem_resultado_perto"] += 1

    por_municipio = []
    regioes = defaultdict(lambda: {"populacao": 0, "contagem": Counter(), "municipios": 0})
    estado = {"populacao": 0, "contagem": Counter()}
    for m in municipios:
        cod = m["codigo_ibge"]
        cont = caps_por_mun.get(cod, Counter())
        pop = m.get("populacao") or 0
        indice = indice_cobertura(cont, pop)
        por_municipio.append({
            "codigo_ibge": cod,
            "nome": m["nome"],
            "regiao": m.get("regiao_saude") or m.get("regiao_imediata"),
            "populacao": pop,
            "caps_total": sum(cont.values()),
            "caps_por_modalidade": dict(cont),
            "indice": round(indice, 3) if indice is not None else None,
            "classificacao": classificar_cobertura(indice),
            "faltam": deficit_por_parametro(cont, pop),
            "buscas_app": demanda[cod]["buscas"] if cod in demanda else 0,
            "buscas_sem_servico_perto": demanda[cod]["sem_resultado_perto"] if cod in demanda else 0,
        })
        reg = regioes[m.get("regiao_saude") or m.get("regiao_imediata") or "Sem região"]
        reg["populacao"] += pop
        reg["contagem"].update(cont)
        reg["municipios"] += 1
        estado["populacao"] += pop
        estado["contagem"].update(cont)

    por_regiao = []
    for nome, r in regioes.items():
        indice = indice_cobertura(r["contagem"], r["populacao"])
        por_regiao.append({
            "regiao": nome,
            "municipios": r["municipios"],
            "populacao": r["populacao"],
            "caps_total": sum(r["contagem"].values()),
            "indice": round(indice, 3) if indice is not None else None,
            "classificacao": classificar_cobertura(indice),
        })
    por_regiao.sort(key=lambda r: (r["indice"] if r["indice"] is not None else 99))
    por_municipio.sort(key=lambda r: (r["indice"] if r["indice"] is not None else 99, -r["populacao"]))

    indice_estado = indice_cobertura(estado["contagem"], estado["populacao"])
    return {
        "estado": {
            "populacao": estado["populacao"],
            "caps_total": sum(estado["contagem"].values()),
            "caps_por_modalidade": dict(estado["contagem"]),
            "indice": round(indice_estado, 3) if indice_estado is not None else None,
            "classificacao": classificar_cobertura(indice_estado),
            "municipios_sem_caps": sum(1 for m in por_municipio if m["caps_total"] == 0),
            "municipios_com_deficit": sum(1 for m in por_municipio if m["faltam"]),
        },
        "municipios": por_municipio,
        "regioes": por_regiao,
    }

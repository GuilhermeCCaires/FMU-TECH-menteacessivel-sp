"""Dados FICTÍCIOS para testes automatizados (não representam unidades reais)."""


def quadrado(lon0, lat0, lado):
    return {"type": "Polygon", "coordinates": [[
        [lon0, lat0], [lon0 + lado, lat0], [lon0 + lado, lat0 + lado],
        [lon0, lat0 + lado], [lon0, lat0]]]}


def malha():
    # Três "municípios" quadrados lado a lado, dentro do território de SP
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": "3500105"}, "geometry": quadrado(-47.0, -23.0, 0.5)},
        {"type": "Feature", "properties": {"codarea": "3500204"}, "geometry": quadrado(-46.5, -23.0, 0.5)},
        {"type": "Feature", "properties": {"codarea": "3500303"}, "geometry": quadrado(-46.0, -23.0, 0.5)},
    ]}


def municipios_ibge():
    return [
        {"codigo_ibge": 3500105, "nome": "Cidade Teste A", "regiao_imediata": "Região X", "regiao_intermediaria": "R1"},
        {"codigo_ibge": 3500204, "nome": "Cidade Teste B", "regiao_imediata": "Região X", "regiao_intermediaria": "R1"},
        {"codigo_ibge": 3500303, "nome": "Cidade Teste C", "regiao_imediata": "Região Y", "regiao_intermediaria": "R1"},
    ]


def populacao():
    return {3500105: 200_000, 3500204: 80_000, 3500303: 10_000}


def registro(cnes, nome, tipo, mun6, lat, lon, turno="ATENDIMENTO NOS TURNOS DA MANHA E A TARDE"):
    return {"cnes": cnes, "nome": nome, "tipo_unidade": tipo, "endereco": "Rua Fictícia, 1",
            "bairro": "Centro", "cep": "00000000", "telefone": "1100000000", "email": None,
            "uf": 35, "municipio": mun6, "lat": lat, "lon": lon, "turno": turno,
            "atende_sus": "SIM", "desabilitado": None, "competencia": "2026-10"}


def registros_cnes():
    h24 = "ATENDIMENTO CONTINUO DE 24 HORAS/DIA (PLANTAO:INCLUI SABADOS, DOMINGOS E FERIADOS)"
    return [
        registro("0000001", "CAPS ADULTO II TESTE", 70, 350010, -22.80, -46.80),
        registro("0000002", "CAPS AD III TESTE", 70, 350010, -22.70, -46.70, h24),
        registro("0000003", "CAPS IJ TESTE", 70, 350010, -22.90, -46.90),
        registro("0000004", "UPA 24H TESTE", 73, 350010, -22.75, -46.75, h24),
        registro("0000005", "UBS VILA TESTE", 2, 350010, -22.79, -46.79),
        registro("0000006", "CAPS I TESTE B", 70, 350020, -22.80, -46.20),
        registro("0000007", "UBS SEM COORDENADA", 2, 350010, None, None),
        registro("0000008", "CLINICA PRIVADA", 36, 350010, -22.8, -46.8),
        {**registro("0000009", "CAPS DESATIVADO", 70, 350010, -22.8, -46.8), "desabilitado": "5"},
        registro("0000010", "UBS CIDADE C", 2, 350030, -22.85, -45.75),
    ]

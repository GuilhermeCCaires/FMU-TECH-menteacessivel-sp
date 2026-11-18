"""Transforma os dados brutos e carrega no banco SQLite.

Mantém as tabelas de uso (evento_busca, reporte) entre cargas: só as tabelas
de referência (unidades, municípios, horários, documentos) são recriadas.
"""
import csv
import json
from datetime import datetime

from app import config, db, geo
from app.classificacao import classificar, normalizar

# Retângulo que contém o Estado de São Paulo (com folga)
SP_LAT = (-25.5, -19.5)
SP_LON = (-53.3, -44.0)


def _dentro_sp(lat, lon):
    return lat is not None and lon is not None and SP_LAT[0] <= lat <= SP_LAT[1] and SP_LON[0] <= lon <= SP_LON[1]


def _corrigir_coordenada(lat, lon, municipio):
    """Valida a coordenada do CNES; se suspeita, usa o centro do município."""
    if lat is not None and lon is not None:
        if not _dentro_sp(lat, lon) and _dentro_sp(lon, lat):
            lat, lon = lon, lat  # latitude e longitude trocadas no cadastro
        if _dentro_sp(lat, lon):
            caixa = municipio.get("bbox") if municipio else None
            if not caixa:
                return lat, lon, "cnes"
            folga = 0.1
            if (caixa[0] - folga <= lon <= caixa[2] + folga and caixa[1] - folga <= lat <= caixa[3] + folga):
                return lat, lon, "cnes"
    if municipio and municipio.get("centro_lat") is not None:
        return municipio["centro_lat"], municipio["centro_lon"], "centro_municipio"
    return None, None, None


def montar_municipios(lista_ibge, populacao, malha_geojson):
    por_codigo = {m["codigo_ibge"]: dict(m) for m in lista_ibge}
    for feature in (malha_geojson or {}).get("features", []):
        props = feature.get("properties") or {}
        cod = props.get("codarea") or props.get("CD_MUN") or props.get("id")
        try:
            cod = int(cod)
        except (TypeError, ValueError):
            continue
        if cod not in por_codigo:
            continue
        geometria = feature.get("geometry")
        lat_lon = geo.centroide(geometria)
        por_codigo[cod].update(
            geometria=geometria,
            bbox=geo.caixa_envolvente(geometria),
            centro_lat=lat_lon[0] if lat_lon else None,
            centro_lon=lat_lon[1] if lat_lon else None,
        )
    for cod, m in por_codigo.items():
        m["populacao"] = populacao.get(cod)
    return por_codigo


def montar_unidades(registros, municipios):
    seis_para_sete = {cod // 10: cod for cod in municipios}
    unidades, descartes = {}, {"inativa": 0, "fora_da_raps": 0, "sem_municipio": 0,
                               "sem_coordenada": 0, "nao_sus": 0}
    for r in registros:
        if r.get("desabilitado") not in (None, "", 0, "0"):
            descartes["inativa"] += 1
            continue
        if normalizar(r.get("atende_sus")) in ("NAO", "N"):
            descartes["nao_sus"] += 1
            continue
        classe = classificar(r.get("tipo_unidade"), r.get("nome"), r.get("turno"))
        if not classe:
            descartes["fora_da_raps"] += 1
            continue
        cod = r.get("municipio")
        cod = seis_para_sete.get(cod, cod) if cod and cod < 1_000_000 else cod
        municipio = municipios.get(cod)
        if not municipio:
            descartes["sem_municipio"] += 1
            continue
        lat, lon, origem = _corrigir_coordenada(r.get("lat"), r.get("lon"), municipio)
        if lat is None:
            descartes["sem_coordenada"] += 1
            continue
        categoria, modalidade, h24 = classe
        unidades[r["cnes"]] = {
            "cnes": r["cnes"], "nome": r.get("nome") or "Unidade sem nome",
            "categoria": categoria, "modalidade": modalidade,
            "tipo_unidade": r.get("tipo_unidade"),
            "endereco": r.get("endereco"), "bairro": r.get("bairro"), "cep": r.get("cep"),
            "telefone": r.get("telefone"), "email": r.get("email"),
            "municipio_ibge": cod, "lat": lat, "lon": lon, "coordenada_origem": origem,
            "turno": r.get("turno"), "funciona_24h": int(bool(h24)),
            "competencia": r.get("competencia"),
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        }
    return list(unidades.values()), descartes


def _ler_csv_curadoria(nome):
    caminho = config.PASTA_CURADORIA / nome
    if not caminho.exists():
        return []
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return [linha for linha in csv.DictReader(f, delimiter=";")
                if any((v or "").strip() for v in linha.values())]


def gravar(unidades, municipios, metadados, caminho_banco=None):
    caminho_banco = caminho_banco or config.CAMINHO_BANCO
    caminho_banco.parent.mkdir(parents=True, exist_ok=True)
    with db.transacao(caminho_banco) as con:
        db.criar_esquema(con)
        for tabela in ("unidade", "municipio", "horario", "documento"):
            con.execute(f"DELETE FROM {tabela}")
        con.executemany(
            "INSERT INTO municipio(codigo_ibge, nome, regiao_imediata, regiao_intermediaria,"
            " regiao_saude, populacao, centro_lat, centro_lon, geometria, bbox)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(m["codigo_ibge"], m["nome"], m.get("regiao_imediata"), m.get("regiao_intermediaria"),
              m.get("regiao_saude"), m.get("populacao"), m.get("centro_lat"), m.get("centro_lon"),
              json.dumps(m["geometria"]) if m.get("geometria") else None,
              json.dumps(m["bbox"]) if m.get("bbox") else None)
             for m in municipios.values()])
        colunas = ["cnes", "nome", "categoria", "modalidade", "tipo_unidade", "endereco", "bairro",
                   "cep", "telefone", "email", "municipio_ibge", "lat", "lon", "coordenada_origem",
                   "turno", "funciona_24h", "competencia", "atualizado_em"]
        con.executemany(
            f"INSERT INTO unidade({','.join(colunas)}) VALUES ({','.join('?' * len(colunas))})",
            [tuple(u[c] for c in colunas) for u in unidades])

        for h in _ler_csv_curadoria("horarios.csv"):
            con.execute("INSERT INTO horario VALUES (?,?,?,?,?,?)", (
                h["cnes"].strip().zfill(7), int(h["dia_semana"]), h["abre"].strip(),
                h["fecha"].strip(), h.get("observacao"), h.get("verificado_em")))
        for d in _ler_csv_curadoria("documentos.csv"):
            chave = d["chave"].strip()
            chave = chave if chave == "padrao" else chave.zfill(7)
            con.execute("INSERT INTO documento VALUES (?,?,?,?)", (
                chave, d["documento"].strip(), int(d.get("obrigatorio") or 0), d.get("observacao")))

        for chave, valor in metadados.items():
            db.definir_metadado(con, chave, valor)

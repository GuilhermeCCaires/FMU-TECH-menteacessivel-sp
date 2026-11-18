"""Banco SQLite: esquema e funções de acesso.

SQLite foi escolhido para o projeto rodar sem instalar servidor de banco.
O esquema segue o modelo do planejamento e pode migrar para PostgreSQL/PostGIS.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS unidade (
    cnes TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL,          -- CAPS | URGENCIA | ATENCAO_BASICA
    modalidade TEXT NOT NULL,         -- CAPS_I, CAPS_II, ..., UPA, UBS
    tipo_unidade INTEGER,
    endereco TEXT, bairro TEXT, cep TEXT, telefone TEXT, email TEXT,
    municipio_ibge INTEGER,
    lat REAL, lon REAL,
    coordenada_origem TEXT,           -- cnes | centro_municipio
    turno TEXT,
    funciona_24h INTEGER DEFAULT 0,
    competencia TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_unidade_municipio ON unidade(municipio_ibge);
CREATE INDEX IF NOT EXISTS ix_unidade_modalidade ON unidade(modalidade);

CREATE TABLE IF NOT EXISTS municipio (
    codigo_ibge INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    regiao_imediata TEXT,
    regiao_intermediaria TEXT,
    regiao_saude TEXT,
    populacao INTEGER,
    centro_lat REAL, centro_lon REAL,
    geometria TEXT,                   -- GeoJSON
    bbox TEXT                         -- [minlon, minlat, maxlon, maxlat]
);

CREATE TABLE IF NOT EXISTS horario (
    cnes TEXT, dia_semana INTEGER,    -- 0 = segunda ... 6 = domingo
    abre TEXT, fecha TEXT, observacao TEXT, verificado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_horario_cnes ON horario(cnes);

CREATE TABLE IF NOT EXISTS documento (
    chave TEXT,                       -- 'padrao' ou código CNES
    documento TEXT, obrigatorio INTEGER, observacao TEXT
);

CREATE TABLE IF NOT EXISTS evento_busca (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT,                   -- arredondada para a hora
    municipio_ibge INTEGER,           -- nunca a coordenada exata
    perfil TEXT,
    resultados INTEGER,
    distancia_primeiro_km REAL
);

CREATE TABLE IF NOT EXISTS reporte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cnes TEXT, tipo TEXT, texto TEXT, criado_em TEXT, status TEXT DEFAULT 'pendente'
);

CREATE TABLE IF NOT EXISTS metadados (chave TEXT PRIMARY KEY, valor TEXT);
"""


def conectar(caminho=None):
    caminho = caminho or config.CAMINHO_BANCO
    conexao = sqlite3.connect(str(caminho), check_same_thread=False)
    conexao.row_factory = sqlite3.Row
    return conexao


@contextmanager
def transacao(caminho=None):
    conexao = conectar(caminho)
    try:
        yield conexao
        conexao.commit()
    finally:
        conexao.close()


def criar_esquema(conexao):
    conexao.executescript(ESQUEMA)


def definir_metadado(conexao, chave, valor):
    conexao.execute("INSERT OR REPLACE INTO metadados(chave, valor) VALUES (?, ?)",
                    (chave, str(valor)))


def ler_metadados(conexao):
    return {r["chave"]: r["valor"] for r in conexao.execute("SELECT chave, valor FROM metadados")}


def registrar_busca(conexao, municipio_ibge, perfil, resultados, distancia_primeiro_km):
    hora = datetime.now().replace(minute=0, second=0, microsecond=0).isoformat(timespec="minutes")
    conexao.execute(
        "INSERT INTO evento_busca(data_hora, municipio_ibge, perfil, resultados, distancia_primeiro_km)"
        " VALUES (?, ?, ?, ?, ?)",
        (hora, municipio_ibge, perfil, resultados, distancia_primeiro_km),
    )
    conexao.commit()


def registrar_reporte(conexao, cnes, tipo, texto):
    conexao.execute(
        "INSERT INTO reporte(cnes, tipo, texto, criado_em) VALUES (?, ?, ?, ?)",
        (cnes, tipo, texto, datetime.now().isoformat(timespec="seconds")),
    )
    conexao.commit()


def carregar_unidades(conexao):
    return [dict(r) for r in conexao.execute("SELECT * FROM unidade")]


def carregar_municipios(conexao, com_geometria=True):
    linhas = []
    for r in conexao.execute("SELECT * FROM municipio"):
        d = dict(r)
        if com_geometria and d.get("geometria"):
            d["geometria"] = json.loads(d["geometria"])
            d["bbox"] = json.loads(d["bbox"]) if d.get("bbox") else None
        else:
            d.pop("geometria", None)
            d.pop("bbox", None)
        linhas.append(d)
    return linhas


def horarios_por_cnes(conexao):
    resultado = {}
    for r in conexao.execute("SELECT * FROM horario ORDER BY dia_semana, abre"):
        resultado.setdefault(r["cnes"], []).append(dict(r))
    return resultado


def documentos(conexao):
    resultado = {}
    for r in conexao.execute("SELECT * FROM documento"):
        resultado.setdefault(r["chave"], []).append(dict(r))
    return resultado

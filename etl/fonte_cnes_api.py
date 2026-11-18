"""Coleta de estabelecimentos de SP na API de dados abertos do Ministério da Saúde.

Endpoint: https://apidadosabertos.saude.gov.br/cnes/estabelecimentos
Documentação: https://apidadosabertos.saude.gov.br/v1/#/
"""
import time
from datetime import date

from app.classificacao import TIPOS_COLETADOS
from . import normalizar
from .rede import baixar_json

URL = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
TAMANHO_PAGINA = 20  # a API devolve no máximo 20 itens por chamada


def _itens(resposta):
    if isinstance(resposta, list):
        return resposta
    if isinstance(resposta, dict):
        for valor in resposta.values():
            if isinstance(valor, list):
                return valor
    return []


def _pagina(tipo, uf, offset):
    return _itens(baixar_json(URL, {
        "codigo_tipo_unidade": tipo,
        "codigo_uf": uf,
        "limit": TAMANHO_PAGINA,
        "offset": offset,
    }))


def _modo_paginacao(tipo, uf):
    """Descobre se 'offset' conta itens ou páginas comparando offset=0 e offset=1."""
    p0, p1 = _pagina(tipo, uf, 0), _pagina(tipo, uf, 1)
    if len(p0) > 1 and p1 and str(p1[0].get("codigo_cnes")) == str(p0[1].get("codigo_cnes")):
        return "itens", p0
    return "paginas", p0


def coletar_tipo(tipo, uf, log=print, pausa=0.15):
    modo, primeira = _modo_paginacao(tipo, uf)
    passo = TAMANHO_PAGINA if modo == "itens" else 1
    vistos, registros = set(), []
    offset, pagina = 0, primeira
    while True:
        novos = 0
        for r in pagina:
            cnes = str(r.get("codigo_cnes"))
            if cnes not in vistos:
                vistos.add(cnes)
                registros.append(r)
                novos += 1
        if len(pagina) < TAMANHO_PAGINA or novos == 0:
            break
        offset += passo
        if offset // passo % 25 == 0:
            log(f"    tipo {tipo}: {len(registros)} registros...")
        time.sleep(pausa)
        pagina = _pagina(tipo, uf, offset)
    return registros


def coletar(uf=35, tipos=TIPOS_COLETADOS, log=print):
    competencia = date.today().strftime("%Y-%m")
    saida = []
    for tipo in tipos:
        log(f"  CNES: baixando tipo de unidade {tipo}...")
        brutos = coletar_tipo(tipo, uf, log)
        for r in brutos:
            reg = normalizar.registro_api(r, competencia)
            # Garante SP mesmo se a API ignorar o filtro de UF
            if reg["uf"] == uf or str(reg["municipio"] or "").startswith(str(uf)):
                saida.append(reg)
        log(f"  CNES: tipo {tipo} -> {len(brutos)} registros")
    return saida

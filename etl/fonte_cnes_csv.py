"""Importação alternativa: base completa do CNES em CSV.

Use quando a API estiver fora do ar. Baixe o arquivo BASE_DE_DADOS_CNES_AAAAMM.ZIP
na área de download do CNES (cnes.datasus.gov.br > Serviços > Download), extraia
numa pasta e rode:  python -m etl.coletar --cnes-csv caminho/da/pasta
São lidos tbEstabelecimentoAAAAMM.csv e, se existir, tbTurnoAtendimentoAAAAMM.csv.
"""
import csv
import re
from pathlib import Path

from app.classificacao import TIPOS_COLETADOS
from . import normalizar

csv.field_size_limit(10_000_000)


def _abrir(caminho):
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            with open(caminho, encoding=codificacao) as f:
                f.read(200_000)
            return open(caminho, encoding=codificacao, newline="")
        except UnicodeDecodeError:
            continue
    return open(caminho, encoding="latin-1", newline="")


def _leitor(arquivo):
    amostra = arquivo.readline()
    arquivo.seek(0)
    separador = ";" if amostra.count(";") >= amostra.count(",") else ","
    return csv.DictReader(arquivo, delimiter=separador)


def _achar(pasta, prefixo):
    candidatos = sorted(p for p in Path(pasta).glob("*.csv") if p.name.lower().startswith(prefixo.lower()))
    return candidatos[-1] if candidatos else None


def coletar(pasta, uf=35, log=print):
    arq_estab = _achar(pasta, "tbEstabelecimento")
    if not arq_estab:
        raise FileNotFoundError(f"Não encontrei tbEstabelecimento*.csv em {pasta}")
    competencia_bruta = re.findall(r"(\d{6})", arq_estab.name)
    competencia = (f"{competencia_bruta[0][:4]}-{competencia_bruta[0][4:]}"
                   if competencia_bruta else None)

    turnos = {}
    arq_turno = _achar(pasta, "tbTurnoAtendimento")
    if arq_turno:
        with _abrir(arq_turno) as f:
            for linha in _leitor(f):
                cod = normalizar.texto(normalizar.pegar(linha, "CO_TURNO_ATENDIMENTO"))
                desc = normalizar.texto(normalizar.pegar(linha, "DS_TURNO_ATENDIMENTO"))
                if cod:
                    turnos[cod.lstrip("0")] = desc

    saida = []
    log(f"  CNES (CSV): lendo {arq_estab.name}...")
    with _abrir(arq_estab) as f:
        for linha in _leitor(f):
            reg = normalizar.registro_csv(linha, turnos, competencia)
            if reg["tipo_unidade"] not in TIPOS_COLETADOS:
                continue
            if reg["uf"] == uf or str(reg["municipio"] or "").startswith(str(uf)):
                saida.append(reg)
    log(f"  CNES (CSV): {len(saida)} estabelecimentos da RAPS em SP")
    return saida

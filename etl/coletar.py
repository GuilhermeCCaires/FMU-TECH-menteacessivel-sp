"""Pipeline completo: baixa CNES + IBGE de SP, transforma e carrega no banco.

Uso:
    python -m etl.coletar                      # baixa tudo pela internet
    python -m etl.coletar --cnes-csv PASTA     # CNES a partir da base em CSV
    python -m etl.coletar --somente-carregar   # reaproveita os brutos já baixados
"""
import argparse
import json
from collections import Counter
from datetime import datetime

from app import config
from app.classificacao import MODALIDADES
from . import carregar, fonte_cnes_api, fonte_cnes_csv, fonte_ibge


def _salvar(nome, dados):
    config.PASTA_BRUTOS.mkdir(parents=True, exist_ok=True)
    with open(config.PASTA_BRUTOS / nome, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)


def _ler(nome):
    with open(config.PASTA_BRUTOS / nome, encoding="utf-8") as f:
        return json.load(f)


def principal(argv=None):
    parser = argparse.ArgumentParser(description="Coleta dados do CNES e do IBGE para SP.")
    parser.add_argument("--cnes-csv", help="pasta com tbEstabelecimento*.csv da base do CNES")
    parser.add_argument("--somente-carregar", action="store_true",
                        help="não baixa nada; usa dados/brutos/")
    args = parser.parse_args(argv)
    uf = config.UF_CODIGO

    if args.somente_carregar:
        print("Usando dados já baixados em dados/brutos/ ...")
        municipios_ibge = _ler("ibge_municipios.json")
        pop_bruta = _ler("ibge_populacao.json")
        populacao = {int(k): v for k, v in pop_bruta["valores"].items()}
        fonte_pop = pop_bruta["fonte"]
        malha = _ler("ibge_malha.geojson")
        cnes = _ler("cnes_sp.json")
        fonte_cnes = _ler("fontes.json").get("cnes", "CNES")
    else:
        print("1/4 IBGE: municípios de SP")
        municipios_ibge = fonte_ibge.municipios(uf)
        _salvar("ibge_municipios.json", municipios_ibge)

        print("2/4 IBGE: população")
        populacao, fonte_pop = fonte_ibge.populacao(uf)
        _salvar("ibge_populacao.json", {"fonte": fonte_pop, "valores": populacao})

        print("3/4 IBGE: malha municipal")
        malha = fonte_ibge.malha(uf)
        _salvar("ibge_malha.geojson", malha)

        print("4/4 CNES: estabelecimentos da RAPS (CAPS, UPA, UBS)")
        if args.cnes_csv:
            cnes = fonte_cnes_csv.coletar(args.cnes_csv, uf)
            fonte_cnes = "CNES/DATASUS - base completa em CSV"
        else:
            cnes = fonte_cnes_api.coletar(uf)
            fonte_cnes = "CNES - API de dados abertos do Ministério da Saúde"
        _salvar("cnes_sp.json", cnes)
        _salvar("fontes.json", {"cnes": fonte_cnes, "populacao": fonte_pop})

    print("Transformando e carregando no banco...")
    municipios = carregar.montar_municipios(municipios_ibge, populacao, malha)
    unidades, descartes = carregar.montar_unidades(cnes, municipios)
    competencias = sorted({u["competencia"] for u in unidades if u.get("competencia")})
    carregar.gravar(unidades, municipios, {
        "data_coleta": datetime.now().isoformat(timespec="minutes"),
        "competencia_cnes": competencias[-1] if competencias else "",
        "fonte_cnes": fonte_cnes,
        "fonte_populacao": fonte_pop,
        "fonte_malha": "IBGE - API de malhas territoriais",
        "total_unidades": len(unidades),
        "total_municipios": len(municipios),
    })

    contagem = Counter(u["modalidade"] for u in unidades)
    aproximadas = sum(1 for u in unidades if u["coordenada_origem"] != "cnes")
    print(f"\nPronto! Banco salvo em {config.CAMINHO_BANCO}")
    print(f"Municípios: {len(municipios)} | com população: {sum(1 for m in municipios.values() if m.get('populacao'))}")
    print(f"Unidades carregadas: {len(unidades)} (coordenada aproximada: {aproximadas})")
    for mod, n in contagem.most_common():
        print(f"  {MODALIDADES.get(mod, mod):40s} {n}")
    print(f"Descartados: {descartes}")


if __name__ == "__main__":
    principal()

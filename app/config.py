"""Configurações centrais do MenteAcessível SP."""
from pathlib import Path
import os

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dados"
PASTA_BRUTOS = PASTA_DADOS / "brutos"
PASTA_CURADORIA = PASTA_DADOS / "curadoria"
PASTA_WEB = RAIZ / "web"

# Pode ser sobrescrito por variável de ambiente (útil nos testes)
CAMINHO_BANCO = Path(os.environ.get("MENTEACESSIVEL_DB", PASTA_DADOS / "menteacessivel.db"))

UF_CODIGO = 35          # São Paulo (código IBGE da UF)
UF_SIGLA = "SP"

HOST = os.environ.get("MENTEACESSIVEL_HOST", "127.0.0.1")
# PORT é a variável usada por serviços de hospedagem (Render, Railway etc.)
PORTA = int(os.environ.get("MENTEACESSIVEL_PORTA") or os.environ.get("PORT") or "8000")

# Raios (km) usados na expansão progressiva da busca
RAIOS_BUSCA_KM = (30, 60, 120, 250)
MIN_RESULTADOS = 3

# Pesos do ranking: S = w1*compat + w2*(1 - d/dmax) + w3*aberto + w4*territorio
PESOS = {"compatibilidade": 0.40, "distancia": 0.35, "aberto": 0.15, "territorio": 0.10}

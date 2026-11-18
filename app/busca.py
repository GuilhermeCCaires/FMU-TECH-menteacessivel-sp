"""Motor de busca: k-NN espacial + ranking ponderado."""
import difflib
from datetime import datetime

from . import config, geo
from .classificacao import (DESCRICAO_SIMPLES, MODALIDADES, PERFIS, compatibilidade,
                            normalizar)
from .kdtree import KDTree

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _minutos(hhmm):
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


def situacao_funcionamento(unidade, horarios, agora=None):
    """Retorna (valor_para_ranking, rotulo, fonte).

    valor: 1 = aberto, 0.5 = provavelmente aberto, 0 = fechado/desconhecido.
    """
    agora = agora or datetime.now()
    if unidade.get("funciona_24h"):
        return 1.0, "Aberto 24 horas", "cnes"

    minuto = agora.hour * 60 + agora.minute
    dia = agora.weekday()
    if horarios:
        for h in horarios:
            if h["dia_semana"] == dia and _minutos(h["abre"]) <= minuto < _minutos(h["fecha"]):
                return 1.0, f"Aberto agora (até {h['fecha']})", "curadoria"
        return 0.0, "Fechado agora", "curadoria"

    # Sem horário verificado: estimativa pelo turno cadastrado no CNES
    turno = normalizar(unidade.get("turno"))
    if dia >= 5:
        return 0.0, "Provavelmente fechado (fim de semana)", "estimado"
    faixas = []
    if "MANHA" in turno:
        faixas.append((7 * 60, 12 * 60))
    if "TARDE" in turno:
        faixas.append((12 * 60, 18 * 60))
    if "NOITE" in turno:
        faixas.append((18 * 60, 22 * 60))
    if not faixas:
        faixas.append((8 * 60, 17 * 60))
    if any(ini <= minuto < fim for ini, fim in faixas):
        return 0.5, "Provavelmente aberto (confirme por telefone)", "estimado"
    return 0.0, "Provavelmente fechado agora", "estimado"


class MotorBusca:
    def __init__(self, unidades, municipios, horarios=None, documentos=None):
        self.unidades = {u["cnes"]: u for u in unidades if u.get("lat") is not None}
        self.municipios = {m["codigo_ibge"]: m for m in municipios}
        self.horarios = horarios or {}
        self.documentos = documentos or {}
        self.arvore = KDTree([(geo.para_vetor(u["lat"], u["lon"]), u["cnes"])
                              for u in self.unidades.values()])
        self._indice_texto = {
            cnes: normalizar(f"{u['nome']} {u.get('bairro') or ''} "
                             f"{self.nome_municipio(u.get('municipio_ibge'))} "
                             f"{MODALIDADES.get(u['modalidade'], '')}")
            for cnes, u in self.unidades.items()
        }

    # ------------------------------------------------------------------ apoio
    def nome_municipio(self, codigo):
        m = self.municipios.get(codigo)
        return m["nome"] if m else ""

    def municipio_do_ponto(self, lat, lon):
        """Ponto-em-polígono sobre a malha do IBGE (com pré-filtro por caixa)."""
        for codigo, m in self.municipios.items():
            geom = m.get("geometria")
            if geom and geo.ponto_na_geometria(lat, lon, geom, m.get("bbox")):
                return codigo
        return None

    def documentos_da_unidade(self, cnes):
        return self.documentos.get(cnes) or self.documentos.get("padrao", [])

    def _formatar(self, u, agora=None):
        valor, rotulo, fonte = situacao_funcionamento(u, self.horarios.get(u["cnes"]), agora)
        return {
            "cnes": u["cnes"],
            "nome": u["nome"],
            "categoria": u["categoria"],
            "modalidade": u["modalidade"],
            "modalidade_nome": MODALIDADES.get(u["modalidade"], u["modalidade"]),
            "descricao": DESCRICAO_SIMPLES.get(u["modalidade"], ""),
            "endereco": u.get("endereco"),
            "bairro": u.get("bairro"),
            "cep": u.get("cep"),
            "telefone": u.get("telefone"),
            "municipio_ibge": u.get("municipio_ibge"),
            "municipio": self.nome_municipio(u.get("municipio_ibge")),
            "lat": u["lat"],
            "lon": u["lon"],
            "coordenada_aproximada": u.get("coordenada_origem") != "cnes",
            "turno": u.get("turno"),
            "funciona_24h": bool(u.get("funciona_24h")),
            "situacao": rotulo,
            "situacao_fonte": fonte,
            "_aberto": valor,
        }

    # ------------------------------------------------------------- consultas
    def proximas(self, lat, lon, perfil="todos", limite=10, agora=None):
        if perfil not in PERFIS:
            perfil = "todos"
        alvo = geo.para_vetor(lat, lon)
        municipio_usuario = self.municipio_do_ponto(lat, lon)

        def aceita(cnes):
            u = self.unidades[cnes]
            return compatibilidade(perfil, u["modalidade"], u.get("funciona_24h")) > 0

        # Etapa 1: k-NN com raio que se expande até achar o mínimo de resultados
        candidatos, raio_usado = [], config.RAIOS_BUSCA_KM[-1]
        for raio in config.RAIOS_BUSCA_KM:
            candidatos = self.arvore.k_vizinhos(alvo, max(limite * 3, 20), aceita,
                                                geo.km_para_corda(raio))
            raio_usado = raio
            if len(candidatos) >= config.MIN_RESULTADOS:
                break

        # Etapa 2: ranking ponderado
        p = config.PESOS
        resultados = []
        for _, cnes in candidatos:
            u = self.unidades[cnes]
            d = geo.haversine_km(lat, lon, u["lat"], u["lon"])
            item = self._formatar(u, agora)
            compat = compatibilidade(perfil, u["modalidade"], u.get("funciona_24h"))
            territorio = 1.0 if municipio_usuario and u.get("municipio_ibge") == municipio_usuario else 0.0
            pontuacao = (p["compatibilidade"] * compat
                         + p["distancia"] * max(0.0, 1 - d / raio_usado)
                         + p["aberto"] * item["_aberto"]
                         + p["territorio"] * territorio)
            item.update(distancia_km=round(d, 2), compatibilidade=compat,
                        mesmo_municipio=bool(territorio), pontuacao=round(pontuacao, 4))
            resultados.append(item)

        resultados.sort(key=lambda r: (-r["pontuacao"], r["distancia_km"]))
        for r in resultados:
            r.pop("_aberto", None)
        return {
            "perfil": perfil,
            "municipio_usuario": municipio_usuario,
            "municipio_usuario_nome": self.nome_municipio(municipio_usuario),
            "raio_km": raio_usado,
            "resultados": resultados[:limite],
        }

    def buscar_texto(self, consulta, municipio=None, perfil="todos", limite=30):
        """Busca por nome/bairro tolerante a acentos e pequenos erros de digitação."""
        termos = normalizar(consulta).split()
        if not termos:
            return []
        achados = []
        for cnes, texto in self._indice_texto.items():
            u = self.unidades[cnes]
            if municipio and u.get("municipio_ibge") != municipio:
                continue
            if compatibilidade(perfil, u["modalidade"], u.get("funciona_24h")) <= 0:
                continue
            palavras = texto.split()
            nota = 0.0
            for termo in termos:
                if termo in texto:
                    nota += 1.0
                else:
                    parecido = difflib.get_close_matches(termo, palavras, n=1, cutoff=0.75)
                    if parecido:
                        nota += 0.7
            if nota >= len(termos) * 0.7:
                achados.append((nota, u["nome"], cnes))
        achados.sort(key=lambda t: (-t[0], t[1]))
        saida = []
        for _, _, cnes in achados[:limite]:
            item = self._formatar(self.unidades[cnes])
            item.pop("_aberto", None)
            saida.append(item)
        return saida

    def ficha(self, cnes):
        u = self.unidades.get(str(cnes))
        if not u:
            return None
        item = self._formatar(u)
        item.pop("_aberto", None)
        item["horarios"] = [
            {**h, "dia_nome": DIAS[h["dia_semana"]]} for h in self.horarios.get(u["cnes"], [])
        ]
        item["documentos"] = self.documentos_da_unidade(u["cnes"])
        item["email"] = u.get("email")
        item["competencia"] = u.get("competencia")
        return item

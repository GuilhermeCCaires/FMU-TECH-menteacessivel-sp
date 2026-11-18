"""Testes dos algoritmos: KD-tree, geografia, classificação, busca e cobertura.

Rodar:  python -m unittest discover -s tests -v
"""
import math
import random
import unittest
from datetime import datetime

from app import geo
from app.busca import MotorBusca, situacao_funcionamento
from app.classificacao import classificar, inferir_modalidade_caps
from app.cobertura import calcular, classificar_cobertura, deficit_por_parametro, indice_cobertura
from app.kdtree import KDTree
from etl import carregar
from tests import sinteticos


class TesteKDTree(unittest.TestCase):
    def test_igual_a_busca_linear(self):
        aleatorio = random.Random(42)
        pontos = [(aleatorio.uniform(-25, -20), aleatorio.uniform(-53, -44)) for _ in range(800)]
        arvore = KDTree([(geo.para_vetor(la, lo), i) for i, (la, lo) in enumerate(pontos)])
        for _ in range(30):
            la, lo = aleatorio.uniform(-25, -20), aleatorio.uniform(-53, -44)
            esperado = sorted(range(len(pontos)),
                              key=lambda i: geo.haversine_km(la, lo, *pontos[i]))[:7]
            obtido = [i for _, i in arvore.k_vizinhos(geo.para_vetor(la, lo), 7)]
            self.assertEqual(obtido, esperado)

    def test_filtro_e_raio(self):
        pontos = [((0.0, 0.0, 1.0), "a"), ((0.0, 0.1, 0.995), "b"), ((0.0, 0.5, 0.866), "c")]
        arvore = KDTree(pontos)
        self.assertEqual([i for _, i in arvore.k_vizinhos((0, 0, 1), 3, filtro=lambda i: i != "a")],
                         ["b", "c"])
        self.assertEqual([i for _, i in arvore.k_vizinhos((0, 0, 1), 3, distancia_max=0.2)],
                         ["a", "b"])


class TesteGeo(unittest.TestCase):
    def test_haversine_sp_campinas(self):
        # Praça da Sé (SP) até o centro de Campinas: cerca de 84 km em linha reta
        d = geo.haversine_km(-23.5505, -46.6333, -22.9056, -47.0608)
        self.assertTrue(80 < d < 90, d)

    def test_corda_ida_e_volta(self):
        self.assertAlmostEqual(geo.corda_para_km(geo.km_para_corda(37.5)), 37.5, places=6)

    def test_ponto_no_poligono_com_buraco(self):
        geom = {"type": "Polygon", "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]]}
        self.assertTrue(geo.ponto_na_geometria(2, 2, geom))
        self.assertFalse(geo.ponto_na_geometria(5, 5, geom))
        self.assertFalse(geo.ponto_na_geometria(11, 5, geom))

    def test_centroide(self):
        lat, lon = geo.centroide(sinteticos.quadrado(-47.0, -23.0, 0.5))
        self.assertAlmostEqual(lat, -22.75)
        self.assertAlmostEqual(lon, -46.75)


class TesteClassificacao(unittest.TestCase):
    def test_modalidades_pelo_nome(self):
        casos = {
            "CAPS AD III SE": "CAPS_AD_III",
            "CAPS ÁLCOOL E DROGAS": "CAPS_AD",
            "CAPS IJ II MOOCA": "CAPS_IJ",
            "CAPS INFANTOJUVENIL": "CAPS_IJ",
            "CAPS ADULTO II ITAQUERA": "CAPS_II",
            "CAPS III LAPA": "CAPS_III",
            "CAPS I DE ITAPIRA": "CAPS_I",
            "CENTRO DE ATENCAO PSICOSSOCIAL": "CAPS_NI",
            "CAPS AD IV CRACOLANDIA": "CAPS_AD_IV",
        }
        for nome, esperado in casos.items():
            self.assertEqual(inferir_modalidade_caps(nome), esperado, nome)

    def test_turno_24h_vira_caps_iii(self):
        self.assertEqual(inferir_modalidade_caps("CAPS CENTRAL", "ATENDIMENTO CONTINUO DE 24 HORAS/DIA"),
                         "CAPS_III")

    def test_classificar_tipos(self):
        self.assertEqual(classificar(73, "UPA 24H", "")[1], "UPA")
        self.assertEqual(classificar(2, "UBS X", "")[0], "ATENCAO_BASICA")
        self.assertIsNone(classificar(36, "CLINICA", ""))


def montar_motor():
    municipios = carregar.montar_municipios(sinteticos.municipios_ibge(), sinteticos.populacao(),
                                            sinteticos.malha())
    unidades, descartes = carregar.montar_unidades(sinteticos.registros_cnes(), municipios)
    return MotorBusca(unidades, list(municipios.values()),
                      documentos={"padrao": [{"documento": "RG"}]}), unidades, municipios, descartes


class TesteETL(unittest.TestCase):
    def test_transformacao(self):
        _, unidades, municipios, descartes = montar_motor()
        por_cnes = {u["cnes"]: u for u in unidades}
        self.assertEqual(descartes["fora_da_raps"], 1)
        self.assertEqual(descartes["inativa"], 1)
        self.assertEqual(por_cnes["0000006"]["municipio_ibge"], 3500204)  # 6 -> 7 dígitos
        self.assertEqual(por_cnes["0000007"]["coordenada_origem"], "centro_municipio")
        self.assertEqual(por_cnes["0000002"]["modalidade"], "CAPS_AD_III")
        self.assertTrue(por_cnes["0000004"]["funciona_24h"])
        self.assertEqual(municipios[3500105]["populacao"], 200_000)


class TesteBusca(unittest.TestCase):
    def setUp(self):
        self.motor = montar_motor()[0]
        self.terca_10h = datetime(2026, 11, 3, 10, 0)

    def test_municipio_do_ponto(self):
        self.assertEqual(self.motor.municipio_do_ponto(-22.8, -46.8), 3500105)
        self.assertEqual(self.motor.municipio_do_ponto(-22.8, -46.2), 3500204)
        self.assertIsNone(self.motor.municipio_do_ponto(-10, -40))

    def test_perfil_infantojuvenil_prioriza_capsij(self):
        r = self.motor.proximas(-22.8, -46.8, "infantojuvenil", agora=self.terca_10h)
        self.assertEqual(r["resultados"][0]["modalidade"], "CAPS_IJ")
        self.assertEqual(r["municipio_usuario"], 3500105)

    def test_crise_so_24h(self):
        r = self.motor.proximas(-22.8, -46.8, "crise", agora=datetime(2026, 11, 8, 3, 0))
        self.assertTrue(r["resultados"])
        self.assertTrue(all(x["funciona_24h"] for x in r["resultados"]))

    def test_alcool_drogas(self):
        r = self.motor.proximas(-22.8, -46.8, "alcool_drogas", agora=self.terca_10h)
        self.assertEqual(r["resultados"][0]["modalidade"], "CAPS_AD_III")

    def test_raio_expande_no_interior(self):
        # Cidade C não tem CAPS: a busca precisa expandir o raio
        r = self.motor.proximas(-22.85, -45.75, "adulto", agora=self.terca_10h)
        self.assertGreaterEqual(r["raio_km"], 60)
        self.assertTrue(any(x["categoria"] == "CAPS" for x in r["resultados"]))

    def test_busca_textual_sem_acento_e_com_erro(self):
        self.assertEqual(self.motor.buscar_texto("caps alcool")[0]["cnes"], "0000002")
        self.assertTrue(self.motor.buscar_texto("upa tste"))

    def test_ficha(self):
        f = self.motor.ficha("0000001")
        self.assertEqual(f["documentos"][0]["documento"], "RG")
        self.assertIsNone(self.motor.ficha("9999999"))

    def test_situacao_funcionamento(self):
        u = {"funciona_24h": 0, "turno": "ATENDIMENTO NOS TURNOS DA MANHA E A TARDE"}
        self.assertEqual(situacao_funcionamento(u, None, self.terca_10h)[0], 0.5)
        self.assertEqual(situacao_funcionamento(u, None, datetime(2026, 11, 3, 23, 0))[0], 0.0)
        h = [{"dia_semana": 1, "abre": "08:00", "fecha": "17:00"}]
        self.assertEqual(situacao_funcionamento(u, h, self.terca_10h)[0], 1.0)


class TesteCobertura(unittest.TestCase):
    def test_formula_oficial(self):
        # 1 CAPS I (0,5) + 1 CAPS III (1,5) em 200 mil hab. = 1,0 por 100 mil
        self.assertAlmostEqual(indice_cobertura({"CAPS_I": 1, "CAPS_III": 1}, 200_000), 1.0)

    def test_faixas(self):
        self.assertEqual(classificar_cobertura(0.71), "Muito boa")
        self.assertEqual(classificar_cobertura(0.70), "Boa")
        self.assertEqual(classificar_cobertura(0.35), "Regular/baixa")
        self.assertEqual(classificar_cobertura(0.19), "Insuficiente/crítica")

    def test_deficit(self):
        self.assertEqual(deficit_por_parametro({}, 10_000), [])
        self.assertIn("CAPS I ou II", deficit_por_parametro({}, 20_000))
        faltam = deficit_por_parametro({"CAPS_II": 1}, 160_000)
        self.assertIn("CAPS III (24h)", faltam)
        self.assertIn("CAPS Infantojuvenil", faltam)

    def test_calcular(self):
        _, unidades, municipios, _ = montar_motor()
        r = calcular(unidades, list(municipios.values()))
        self.assertEqual(r["estado"]["caps_total"], 4)
        a = next(m for m in r["municipios"] if m["codigo_ibge"] == 3500105)
        # CAPS II (1) + AD III (1,5) + IJ (1) = 3,5 / 200 mil * 100 mil = 1,75
        self.assertAlmostEqual(a["indice"], 1.75)
        self.assertTrue(math.isclose(r["estado"]["populacao"], 290_000))


if __name__ == "__main__":
    unittest.main()

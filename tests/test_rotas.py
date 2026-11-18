"""Testes das rotas (sem acessar a internet: o servidor OSRM é simulado)."""
import unittest
import urllib.parse

from app import rotas

RESPOSTA_OSRM = {
    "code": "Ok",
    "routes": [{
        "distance": 1834.6, "duration": 1320.2,
        "geometry": {"type": "LineString", "coordinates": [[-46.80, -22.80], [-46.79, -22.795], [-46.78, -22.79]]},
        "legs": [{"steps": [
            {"name": "Rua das Flores", "distance": 300, "maneuver": {"type": "depart"}},
            {"name": "Avenida Brasil", "distance": 800, "maneuver": {"type": "turn", "modifier": "left"}},
            {"name": "Avenida Brasil", "distance": 200, "maneuver": {"type": "continue", "modifier": "straight"}},
            {"name": "Avenida Brasil", "distance": 100, "maneuver": {"type": "continue", "modifier": "straight"}},
            {"name": "", "distance": 400, "maneuver": {"type": "roundabout", "exit": 2}},
            {"name": "Rua do CAPS", "distance": 0, "maneuver": {"type": "arrive", "modifier": "right"}},
        ]}],
    }],
}


class TesteInstrucoes(unittest.TestCase):
    def passo(self, tipo, mod=None, nome="Rua A", **extra):
        m = {"type": tipo, **({"modifier": mod} if mod else {}), **extra}
        return {"name": nome, "maneuver": m}

    def test_frases(self):
        casos = [
            (self.passo("depart"), "Comece pela Rua A"),
            (self.passo("turn", "right"), "Vire à direita na Rua A"),
            (self.passo("turn", "slight left"), "Mantenha-se à esquerda na Rua A"),
            (self.passo("turn", "uturn"), "Faça o retorno na Rua A"),
            (self.passo("new name", "straight"), "Continue pela Rua A"),
            (self.passo("roundabout", exit=3), "Na rotatória, pegue a 3ª saída para Rua A"),
            (self.passo("fork", "slight right"), "Na bifurcação, mantenha-se à direita para Rua A"),
            (self.passo("end of road", "left"), "No fim da via, vire à esquerda na Rua A"),
            (self.passo("turn", "left", nome=""), "Vire à esquerda na via sem nome"),
            (self.passo("arrive", "left"), "Chegada: CAPS X, à esquerda"),
        ]
        for passo, esperado in casos:
            self.assertEqual(rotas.instrucao(passo, "CAPS X"), esperado)

    def test_referencia_da_rodovia(self):
        p = {"name": "", "ref": "SP-330", "maneuver": {"type": "on ramp"}}
        self.assertEqual(rotas.instrucao(p), "Pegue o acesso para SP-330")


class TesteMontarRota(unittest.TestCase):
    def test_resumo_e_passos(self):
        r = rotas.montar_rota(RESPOSTA_OSRM, "a_pe", "CAPS Teste")
        self.assertEqual(r["distancia_m"], 1835)
        self.assertEqual(r["duracao_s"], 1320)
        self.assertEqual(len(r["geometria"]), 3)
        textos = [p["instrucao"] for p in r["passos"]]
        # "Continue pela Avenida Brasil" repetido vira um passo só
        self.assertEqual(textos.count("Continue pela Avenida Brasil"), 1)
        self.assertEqual(r["passos"][2]["distancia_m"], 300)
        self.assertEqual(textos[-1], "Chegada: CAPS Teste, à direita")

    def test_erro_do_servidor(self):
        with self.assertRaises(rotas.ErroRota):
            rotas.montar_rota({"code": "NoRoute", "routes": []}, "carro", "X")


class TesteCalcular(unittest.TestCase):
    def setUp(self):
        rotas._cache.clear()
        self.chamadas = []

    def baixar(self, url, parametros=None, **_):
        self.chamadas.append((url, parametros))
        return RESPOSTA_OSRM

    def test_url_e_cache(self):
        o, d = (-22.8, -46.8), (-22.79, -46.78)
        r1 = rotas.calcular("carro", o, d, "CAPS", baixar=self.baixar)
        r2 = rotas.calcular("carro", (-22.80001, -46.80001), d, "CAPS", baixar=self.baixar)
        self.assertEqual(len(self.chamadas), 1)  # segunda veio do cache
        self.assertIs(r1, r2)
        url, params = self.chamadas[0]
        self.assertIn("/routed-car/route/v1/driving/-46.8,-22.8;-46.78,-22.79", url)
        self.assertEqual(params["geometries"], "geojson")
        rotas.calcular("a_pe", o, d, "CAPS", baixar=self.baixar)
        self.assertIn("/routed-foot/", self.chamadas[-1][0])

    def test_limites(self):
        with self.assertRaises(rotas.ErroRota):
            rotas.calcular("carro", (-22.8, -46.8), (-20.0, -49.9), "X", baixar=self.baixar)
        with self.assertRaises(rotas.ErroRota):
            rotas.calcular("aviao", (-22.8, -46.8), (-22.7, -46.7), "X", baixar=self.baixar)

    def test_servidor_fora_do_ar(self):
        def falha(*_a, **_k):
            raise RuntimeError("timeout")
        with self.assertRaises(rotas.ErroRota):
            rotas.calcular("a_pe", (-22.8, -46.8), (-22.7, -46.7), "X", baixar=falha)


class TesteLinks(unittest.TestCase):
    def test_links_por_modo(self):
        links = rotas.links_externos((-22.8, -46.8), (-22.7, -46.7), "CAPS AD III Sé")
        transporte = links["transporte"][0]["url"]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(transporte).query)
        self.assertEqual(q["travelmode"], ["transit"])
        self.assertEqual(q["origin"], ["-22.8,-46.8"])
        self.assertEqual(q["destination"], ["-22.7,-46.7"])
        moovit = urllib.parse.parse_qs(urllib.parse.urlparse(links["transporte"][1]["url"]).query)
        self.assertEqual(moovit["tll"], ["-22.7_-46.7"])
        self.assertEqual(moovit["to"], ["CAPS AD III Sé"])
        self.assertIn("waze.com/ul", links["carro"][1]["url"])
        self.assertIn("travelmode=walking", links["a_pe"][0]["url"])

    def test_sem_origem(self):
        url = rotas.links_externos(None, (-22.7, -46.7), "X")["transporte"][0]["url"]
        self.assertNotIn("origin=", url)


if __name__ == "__main__":
    unittest.main()

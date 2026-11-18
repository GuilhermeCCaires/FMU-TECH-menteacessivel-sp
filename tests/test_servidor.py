"""Teste de ponta a ponta: ETL sintético -> SQLite -> servidor HTTP -> rotas da API."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from app import servidor
from etl import carregar
from tests import sinteticos


class TesteServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        banco = Path(cls.pasta.name) / "teste.db"
        municipios = carregar.montar_municipios(sinteticos.municipios_ibge(), sinteticos.populacao(),
                                                sinteticos.malha())
        unidades, _ = carregar.montar_unidades(sinteticos.registros_cnes(), municipios)
        carregar.gravar(unidades, municipios, {"competencia_cnes": "2026-10"}, banco)
        cls.http, cls.estado = servidor.iniciar("127.0.0.1", 0, banco)
        cls.base = f"http://127.0.0.1:{cls.http.server_address[1]}"
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.estado.conexao.close()
        cls.pasta.cleanup()

    def get(self, caminho):
        with urllib.request.urlopen(self.base + caminho) as r:
            corpo = r.read()
            return r.status, r.headers.get("Content-Type"), corpo

    def get_json(self, caminho):
        return json.loads(self.get(caminho)[2])

    def test_status(self):
        s = self.get_json("/api/status")
        self.assertTrue(s["pronto"])
        self.assertEqual(s["metadados"]["competencia_cnes"], "2026-10")

    def test_proximas_registra_evento(self):
        r = self.get_json("/api/unidades/proximas?lat=-22.8&lon=-46.8&perfil=alcool_drogas")
        self.assertEqual(r["resultados"][0]["cnes"], "0000002")
        demanda = self.get_json("/api/demanda")
        self.assertGreaterEqual(demanda["total"], 1)
        self.assertEqual(demanda["municipios"][0]["codigo_ibge"], 3500105)

    def test_proximas_parametros_invalidos(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/unidades/proximas?lat=abc&lon=1")
        self.assertEqual(ctx.exception.code, 400)

    def test_ficha_e_404(self):
        self.assertEqual(self.get_json("/api/unidades/0000003")["modalidade"], "CAPS_IJ")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/unidades/1234567")
        self.assertEqual(ctx.exception.code, 404)

    def test_busca_texto_municipios_caps(self):
        self.assertTrue(self.get_json("/api/unidades/busca?q=caps%20ij"))
        self.assertEqual(len(self.get_json("/api/municipios")), 3)
        self.assertEqual(len(self.get_json("/api/unidades/caps")), 4)

    def test_cobertura_e_malha(self):
        c = self.get_json("/api/cobertura")
        self.assertEqual(c["estado"]["caps_total"], 4)
        self.assertEqual(len(self.get_json("/api/malha")["features"]), 3)

    def test_reporte(self):
        pedido = urllib.request.Request(self.base + "/api/reportes", method="POST",
                                        data=json.dumps({"cnes": "0000001", "tipo": "telefone_errado",
                                                         "texto": "não atende"}).encode(),
                                        headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(pedido) as r:
            self.assertEqual(r.status, 201)
        ruim = urllib.request.Request(self.base + "/api/reportes", method="POST",
                                      data=b'{"cnes":"x","tipo":"y"}')
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(ruim)

    def test_paginas_estaticas(self):
        for caminho, tipo in [("/", "text/html"), ("/buscar", "text/html"), ("/inicio.js", "text/javascript"),
                              ("/painel", "text/html"), ("/sobre", "text/html"),
                              ("/app.js", "text/javascript"), ("/estilo.css", "text/css"),
                              ("/manifest.webmanifest", "application/manifest+json"),
                              ("/icone-192.png", "image/png"), ("/apple-touch-icon.png", "image/png")]:
            status, ctype, _ = self.get(caminho)
            self.assertEqual(status, 200)
            self.assertTrue(ctype.startswith(tipo), (caminho, ctype))

    def test_menu_inicial_e_busca(self):
        inicio = self.get("/")[2].decode("utf-8")
        self.assertIn("Precisa de ajuda agora?", inicio)
        self.assertIn('href="tel:188"', inicio)
        self.assertIn("/buscar?perfil=infantojuvenil", inicio)
        busca = self.get("/buscar")[2].decode("utf-8")
        self.assertIn('id="mapa"', busca)

    def test_manifesto_instalavel(self):
        m = self.get_json("/manifest.webmanifest")
        tamanhos = {i["sizes"] for i in m["icons"] if i["type"] == "image/png"}
        self.assertTrue({"192x192", "512x512"} <= tamanhos)
        self.assertEqual(m["display"], "standalone")

    def test_ip_rede_local(self):
        ip = servidor.ip_na_rede_local()
        self.assertTrue(ip is None or ip.count(".") == 3)

    def test_rota_transporte_publico(self):
        r = self.get_json("/api/rota?cnes=0000001&modo=transporte&lat=-22.75&lon=-46.75")
        self.assertIsNone(r["rota"])
        self.assertIn("travelmode=transit", r["links"][0]["url"])
        self.assertGreater(r["distancia_reta_km"], 0)

    def test_rota_a_pe_com_servidor_simulado(self):
        falsa = {"modo": "a_pe", "distancia_m": 900, "duracao_s": 700, "geometria": [], "passos": []}
        with mock.patch("app.rotas.calcular", return_value=falsa) as calc:
            r = self.get_json("/api/rota?cnes=0000001&modo=a_pe&lat=-22.79&lon=-46.79")
        self.assertEqual(r["rota"]["distancia_m"], 900)
        self.assertEqual(calc.call_args.args[1], (-22.79, -46.79))

    def test_rota_servidor_fora_do_ar(self):
        from app import rotas
        with mock.patch("app.rotas.calcular", side_effect=rotas.ErroRota("Servidor de rotas indisponível.")):
            r = self.get_json("/api/rota?cnes=0000001&modo=carro&lat=-22.79&lon=-46.79")
        self.assertIsNone(r["rota"])
        self.assertIn("indisponível", r["aviso"])
        self.assertTrue(r["links"])  # links externos continuam disponíveis

    def test_rota_sem_origem_e_erros(self):
        r = self.get_json("/api/rota?cnes=0000001&modo=a_pe")
        self.assertIn("localização", r["aviso"])
        for caminho, codigo in [("/api/rota?cnes=9999999&modo=a_pe", 404),
                                ("/api/rota?cnes=0000001&modo=aviao", 400)]:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(caminho)
            self.assertEqual(ctx.exception.code, codigo)

    def test_nao_sai_da_pasta_web(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/..%2fapp%2fconfig.py")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

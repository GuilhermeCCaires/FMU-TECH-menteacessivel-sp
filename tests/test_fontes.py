"""Testes da coleta com respostas simuladas das APIs (sem acessar a internet)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from etl import fonte_cnes_api, fonte_cnes_csv, fonte_ibge


def api_falsa(total, modo):
    """Simula a API do CNES com `total` estabelecimentos e paginação por itens ou páginas."""
    base = [{"codigo_cnes": 1000 + i, "nome_fantasia": f"CAPS II TESTE {i}", "codigo_tipo_unidade": 70,
             "codigo_uf": 35, "codigo_municipio": 350010,
             "latitude_estabelecimento_decimo_grau": -22.8, "longitude_estabelecimento_decimo_grau": -46.8,
             "descricao_turno_atendimento": "ATENDIMENTO NOS TURNOS DA MANHA E A TARDE"} for i in range(total)]

    def baixar(url, parametros=None, **_):
        inicio = parametros["offset"] if modo == "itens" else parametros["offset"] * parametros["limit"]
        return {"estabelecimentos": base[inicio:inicio + parametros["limit"]]}
    return baixar


class TesteCnesApi(unittest.TestCase):
    def test_paginacao_por_itens(self):
        with mock.patch.object(fonte_cnes_api, "baixar_json", api_falsa(53, "itens")), \
             mock.patch.object(fonte_cnes_api.time, "sleep"):
            regs = fonte_cnes_api.coletar(35, tipos=(70,), log=lambda *_: None)
        self.assertEqual(len(regs), 53)
        self.assertEqual(regs[0]["cnes"], "0001000")
        self.assertEqual(regs[0]["lat"], -22.8)

    def test_paginacao_por_paginas(self):
        with mock.patch.object(fonte_cnes_api, "baixar_json", api_falsa(41, "paginas")), \
             mock.patch.object(fonte_cnes_api.time, "sleep"):
            regs = fonte_cnes_api.coletar(35, tipos=(70,), log=lambda *_: None)
        self.assertEqual(len(regs), 41)


class TesteIbge(unittest.TestCase):
    def test_municipios_e_populacao(self):
        municipios = [{"id": 3550308, "nome": "São Paulo", "regiao-imediata": {
            "nome": "São Paulo", "regiao-intermediaria": {"nome": "São Paulo"}}}]
        populacao = [{"id": "93", "resultados": [{"series": [
            {"localidade": {"id": "3550308"}, "serie": {"2022": "11451999"}}]}]}]
        with mock.patch.object(fonte_ibge, "baixar_json", side_effect=[municipios, populacao]):
            self.assertEqual(fonte_ibge.municipios()[0]["regiao_imediata"], "São Paulo")
            valores, fonte = fonte_ibge.populacao()
        self.assertEqual(valores[3550308], 11451999)
        self.assertIn("Censo", fonte)


class TesteCnesCsv(unittest.TestCase):
    def test_importacao_csv(self):
        with tempfile.TemporaryDirectory() as pasta:
            Path(pasta, "tbEstabelecimento202610.csv").write_text(
                '"CO_CNES";"NO_FANTASIA";"TP_UNIDADE";"CO_ESTADO_GESTOR";"CO_MUNICIPIO_GESTOR";'
                '"NU_LATITUDE";"NU_LONGITUDE";"CO_TURNO_ATENDIMENTO"\n'
                '"1234567";"CAPS AD III TESTE";"70";"35";"350010";"-22,8";"-46,8";"06"\n'
                '"7654321";"CONSULTORIO";"22";"35";"350010";"-22,8";"-46,8";"03"\n'
                '"1111111";"CAPS DE OUTRO ESTADO";"70";"33";"330455";"-22,9";"-43,2";"03"\n',
                encoding="latin-1")
            Path(pasta, "tbTurnoAtendimento202610.csv").write_text(
                '"CO_TURNO_ATENDIMENTO";"DS_TURNO_ATENDIMENTO"\n'
                '"06";"ATENDIMENTO CONTINUO DE 24 HORAS/DIA"\n', encoding="latin-1")
            regs = fonte_cnes_csv.coletar(pasta, 35, log=lambda *_: None)
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["competencia"], "2026-10")
        self.assertEqual(regs[0]["lat"], -22.8)
        self.assertIn("24 HORAS", regs[0]["turno"])


class TesteDecodificacao(unittest.TestCase):
    def test_gzip_sem_cabecalho(self):
        import gzip
        from etl.rede import decodificar
        texto = '[{"nome": "São Paulo"}]'
        self.assertEqual(decodificar(gzip.compress(texto.encode("utf-8"))), texto)
        self.assertEqual(decodificar(texto.encode("utf-8")), texto)
        self.assertEqual(decodificar(texto.encode("latin-1")), texto)


if __name__ == "__main__":
    unittest.main()

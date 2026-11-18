"""Testes do acesso pelo celular (cloudflared simulado; não acessa a internet)."""
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from app import celular

LINHA_REAL = "2026-11-13T19:22:41Z INF |  https://kingston-inside-best-graphic.trycloudflare.com                |"


class TesteLink(unittest.TestCase):
    def test_extrair_link(self):
        self.assertEqual(celular.extrair_link(LINHA_REAL),
                         "https://kingston-inside-best-graphic.trycloudflare.com")
        self.assertIsNone(celular.extrair_link("INF Requesting new quick Tunnel on trycloudflare.com..."))
        self.assertIsNone(celular.extrair_link(None))


class TesteRedeLocal(unittest.TestCase):
    def test_wifi_de_casa_primeiro_e_virtuais_por_ultimo(self):
        def falso(*_a, **_k):
            ips = ["172.25.48.1", "127.0.0.1", "192.168.56.1", "192.168.0.15", "169.254.10.2", "10.0.0.7"]
            return [(None, None, None, None, (ip, 0)) for ip in ips]
        with mock.patch.object(celular.socket, "getaddrinfo", falso), \
             mock.patch.object(celular.servidor, "ip_na_rede_local", return_value="192.168.0.15"):
            ips = celular.ips_na_rede_local()
        self.assertEqual(ips, ["192.168.0.15", "10.0.0.7", "172.25.48.1", "192.168.56.1"])


class TesteEncontrarCloudflared(unittest.TestCase):
    def test_pasta_ferramentas(self):
        with tempfile.TemporaryDirectory() as pasta:
            nome = "cloudflared.exe" if os.name == "nt" else "cloudflared"
            Path(pasta, nome).write_text("x")
            with mock.patch.object(celular, "PASTA_FERRAMENTAS", Path(pasta)), \
                 mock.patch.object(celular.shutil, "which", return_value=None), \
                 mock.patch.dict(os.environ, {"ProgramFiles": pasta + "_nao", "ProgramFiles(x86)": pasta + "_nao",
                                              "LOCALAPPDATA": pasta + "_nao"}):
                self.assertEqual(celular.encontrar_cloudflared(), str(Path(pasta, nome)))

    def test_nome_do_download(self):
        with mock.patch.object(celular.platform, "system", return_value="Windows"), \
             mock.patch.object(celular.platform, "machine", return_value="AMD64"):
            self.assertEqual(celular._nome_arquivo_cloudflared(), "cloudflared-windows-amd64.exe")


@unittest.skipIf(os.name == "nt", "o cloudflared falso é um script de shell")
class TesteTunel(unittest.TestCase):
    def test_tunel_com_cloudflared_falso(self):
        with tempfile.TemporaryDirectory() as pasta:
            falso = Path(pasta, "cloudflared")
            falso.write_text(textwrap.dedent(f"""\
                #!{sys.executable}
                import sys, time
                print("INF Requesting new quick Tunnel on trycloudflare.com...", flush=True)
                print("{LINHA_REAL}", flush=True)
                print("args:", " ".join(sys.argv[1:]), flush=True)
                time.sleep(30)
                """))
            falso.chmod(0o755)
            log = []
            processo, link = celular.iniciar_tunel(str(falso), 8123, espera_max=10, log=log)
            try:
                self.assertEqual(link, "https://kingston-inside-best-graphic.trycloudflare.com")
                self.assertIsNone(processo.poll())  # túnel continua rodando
            finally:
                processo.terminate()
                processo.wait(5)
                processo.stdout.close()
            self.assertTrue(any("--url http://127.0.0.1:8123" in linha for linha in log))

    def test_tunel_sem_link(self):
        with tempfile.TemporaryDirectory() as pasta:
            falso = Path(pasta, "cloudflared")
            falso.write_text(f"#!{sys.executable}\nprint('ERR failed to connect', flush=True)\n")
            falso.chmod(0o755)
            with self.assertRaises(RuntimeError):
                celular.iniciar_tunel(str(falso), 8123, espera_max=5)


if __name__ == "__main__":
    unittest.main()

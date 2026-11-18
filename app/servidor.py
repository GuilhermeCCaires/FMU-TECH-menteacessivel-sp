"""Servidor web do MenteAcessível SP (somente biblioteca padrão do Python).

Uso:  python -m app.servidor      e abra http://127.0.0.1:8000
"""
import json
import mimetypes
import threading
from collections import Counter, defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import config, db, geo, rotas
from .busca import MotorBusca
from .classificacao import MODALIDADES, PERFIS
from .cobertura import calcular

# Preenchido por app/celular.py: links para abrir o app no celular
ACESSO_CELULAR = {}

TIPOS_REPORTE = {"telefone_errado", "endereco_errado", "unidade_fechada", "horario_errado", "outro"}


class Estado:
    """Dados carregados em memória na inicialização (recarregáveis)."""

    def __init__(self, caminho_banco=None):
        self.caminho = caminho_banco or config.CAMINHO_BANCO
        self.trava = threading.Lock()
        self.pronto = False
        self.carregar()

    def carregar(self):
        if not self.caminho.exists():
            self.pronto = False
            return
        self.conexao = db.conectar(self.caminho)
        db.criar_esquema(self.conexao)
        unidades = db.carregar_unidades(self.conexao)
        municipios = db.carregar_municipios(self.conexao)
        self.unidades = unidades
        self.municipios = municipios
        self.motor = MotorBusca(unidades, municipios, db.horarios_por_cnes(self.conexao),
                                db.documentos(self.conexao))
        self.metadados = db.ler_metadados(self.conexao)
        self.malha = json.dumps({
            "type": "FeatureCollection",
            "features": [{"type": "Feature",
                          "properties": {"codigo_ibge": m["codigo_ibge"], "nome": m["nome"]},
                          "geometry": m["geometria"]}
                         for m in municipios if m.get("geometria")],
        }, separators=(",", ":")).encode("utf-8")
        self.pronto = bool(unidades)

    def eventos(self):
        with self.trava:
            return [dict(r) for r in self.conexao.execute("SELECT * FROM evento_busca")]


def _numero(valor, padrao=None):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def criar_manipulador(estado):
    class Manipulador(BaseHTTPRequestHandler):
        server_version = "MenteAcessivel/1.0"

        # ------------------------------------------------------------ respostas
        def _json(self, dados, status=HTTPStatus.OK):
            corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self._enviar(corpo, "application/json; charset=utf-8", status)

        def _enviar(self, corpo, tipo, status=HTTPStatus.OK, cache="no-cache"):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _erro(self, status, mensagem):
            self._json({"erro": mensagem}, status)

        def log_message(self, formato, *args):  # log mais enxuto
            if not self.path.startswith("/api/"):
                return
            super().log_message(formato, *args)

        # ---------------------------------------------------------------- GET
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path.startswith("/api/"):
                if url.path not in ("/api/status", "/api/perfis", "/api/celular") and not estado.pronto:
                    return self._erro(HTTPStatus.SERVICE_UNAVAILABLE,
                                      "Banco de dados vazio. Rode: python -m etl.coletar")
                try:
                    return self._rotear_api(url.path, q)
                except Exception as erro:  # noqa: BLE001 - resposta amigável
                    self.log_error("Erro: %r", erro)
                    return self._erro(HTTPStatus.INTERNAL_SERVER_ERROR, "Erro interno")
            return self._estatico(url.path)

        def _rotear_api(self, caminho, q):
            if caminho == "/api/status":
                return self._json({"pronto": estado.pronto,
                                   "metadados": getattr(estado, "metadados", {}),
                                   "uf": config.UF_SIGLA})
            if caminho == "/api/celular":
                return self._json(ACESSO_CELULAR or {"situacao": "Rode: python -m app.celular"})
            if caminho == "/api/perfis":
                return self._json({"perfis": PERFIS, "modalidades": MODALIDADES})
            if caminho == "/api/municipios":
                return self._json([{
                    "codigo_ibge": m["codigo_ibge"], "nome": m["nome"],
                    "lat": m.get("centro_lat"), "lon": m.get("centro_lon"),
                    "populacao": m.get("populacao"),
                } for m in sorted(estado.municipios, key=lambda m: m["nome"])])
            if caminho == "/api/unidades/proximas":
                return self._proximas(q)
            if caminho == "/api/unidades/busca":
                municipio = int(q["municipio"]) if q.get("municipio", "").isdigit() else None
                return self._json(estado.motor.buscar_texto(q.get("q", ""), municipio,
                                                             q.get("perfil", "todos")))
            if caminho == "/api/unidades/caps":
                return self._json([{
                    "cnes": u["cnes"], "nome": u["nome"], "modalidade": u["modalidade"],
                    "lat": u["lat"], "lon": u["lon"],
                } for u in estado.unidades if u["categoria"] == "CAPS"])
            if caminho.startswith("/api/unidades/"):
                ficha = estado.motor.ficha(unquote(caminho.rsplit("/", 1)[-1]))
                return self._json(ficha) if ficha else self._erro(HTTPStatus.NOT_FOUND,
                                                                  "Unidade não encontrada")
            if caminho == "/api/cobertura":
                resultado = calcular(estado.unidades, estado.municipios, estado.eventos())
                resultado["metadados"] = estado.metadados
                return self._json(resultado)
            if caminho == "/api/malha":
                return self._enviar(estado.malha, "application/geo+json", cache="max-age=86400")
            if caminho == "/api/demanda":
                return self._demanda()
            if caminho == "/api/rota":
                return self._rota(q)
            return self._erro(HTTPStatus.NOT_FOUND, "Rota não encontrada")

        def _proximas(self, q):
            lat, lon = _numero(q.get("lat")), _numero(q.get("lon"))
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return self._erro(HTTPStatus.BAD_REQUEST, "Informe lat e lon válidos")
            limite = int(min(max(_numero(q.get("limite"), 10), 1), 50))
            resposta = estado.motor.proximas(lat, lon, q.get("perfil", "todos"), limite)
            if q.get("registrar", "1") == "1":
                primeiro = resposta["resultados"][0]["distancia_km"] if resposta["resultados"] else None
                with estado.trava:
                    db.registrar_busca(estado.conexao, resposta["municipio_usuario"],
                                       resposta["perfil"], len(resposta["resultados"]), primeiro)
            return self._json(resposta)

        def _rota(self, q):
            """Rota da origem informada até a unidade. A origem não é guardada."""
            unidade = estado.motor.unidades.get(q.get("cnes", ""))
            if not unidade:
                return self._erro(HTTPStatus.NOT_FOUND, "Unidade não encontrada")
            modo = q.get("modo", "a_pe")
            if modo not in rotas.MODOS:
                return self._erro(HTTPStatus.BAD_REQUEST, "Modo deve ser transporte, carro ou a_pe")
            lat, lon = _numero(q.get("lat")), _numero(q.get("lon"))
            origem = (lat, lon) if lat is not None and lon is not None else None
            if origem and not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return self._erro(HTTPStatus.BAD_REQUEST, "Origem inválida")
            destino = (unidade["lat"], unidade["lon"])
            resposta = {
                "modo": modo,
                "destino": {"cnes": unidade["cnes"], "nome": unidade["nome"],
                            "lat": destino[0], "lon": destino[1]},
                "links": rotas.links_externos(origem, destino, unidade["nome"])[modo],
                "distancia_reta_km": round(geo.haversine_km(*origem, *destino), 2) if origem else None,
                "rota": None,
                "aviso": None,
            }
            if modo != "transporte":
                if not origem:
                    resposta["aviso"] = "Informe sua localização para calcular a rota."
                else:
                    try:
                        resposta["rota"] = rotas.calcular(modo, origem, destino, unidade["nome"])
                    except rotas.ErroRota as erro:
                        resposta["aviso"] = f"{erro} Use um dos links abaixo."
            return self._json(resposta)

        def _demanda(self):
            eventos = estado.eventos()
            nomes = {m["codigo_ibge"]: m["nome"] for m in estado.municipios}
            por_dia, por_perfil, por_mun = Counter(), Counter(), defaultdict(lambda: [0, 0])
            for e in eventos:
                por_dia[(e["data_hora"] or "")[:10]] += 1
                por_perfil[e["perfil"]] += 1
                if e["municipio_ibge"]:
                    reg = por_mun[e["municipio_ibge"]]
                    reg[0] += 1
                    if not e["resultados"] or (e["distancia_primeiro_km"] or 0) > 30:
                        reg[1] += 1
            return self._json({
                "total": len(eventos),
                "por_dia": sorted(por_dia.items()),
                "por_perfil": por_perfil.most_common(),
                "municipios": sorted(
                    ({"codigo_ibge": c, "nome": nomes.get(c, str(c)), "buscas": v[0],
                      "sem_servico_perto": v[1]} for c, v in por_mun.items()),
                    key=lambda r: -r["buscas"])[:30],
            })

        # --------------------------------------------------------------- POST
        def do_POST(self):
            if urlparse(self.path).path != "/api/reportes":
                return self._erro(HTTPStatus.NOT_FOUND, "Rota não encontrada")
            if not estado.pronto:
                return self._erro(HTTPStatus.SERVICE_UNAVAILABLE, "Banco de dados vazio")
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho > 10_000:
                return self._erro(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Mensagem muito longa")
            try:
                dados = json.loads(self.rfile.read(tamanho) or b"{}")
            except json.JSONDecodeError:
                return self._erro(HTTPStatus.BAD_REQUEST, "JSON inválido")
            cnes = str(dados.get("cnes", "")).strip()
            tipo = dados.get("tipo")
            if cnes not in estado.motor.unidades or tipo not in TIPOS_REPORTE:
                return self._erro(HTTPStatus.BAD_REQUEST, "Unidade ou tipo de reporte inválido")
            texto = str(dados.get("texto", ""))[:500]
            with estado.trava:
                db.registrar_reporte(estado.conexao, cnes, tipo, texto)
            return self._json({"ok": True}, HTTPStatus.CREATED)

        # ---------------------------------------------------------- estáticos
        def _estatico(self, caminho):
            paginas = {"/": "inicio.html", "/buscar": "index.html", "/painel": "painel.html",
                       "/sobre": "sobre.html", "/celular": "celular.html"}
            nome = paginas.get(caminho, caminho.lstrip("/"))
            arquivo = (config.PASTA_WEB / unquote(nome)).resolve()
            if config.PASTA_WEB.resolve() not in arquivo.parents or not arquivo.is_file():
                return self._erro(HTTPStatus.NOT_FOUND, "Página não encontrada")
            # Tipos fixos: no Windows o registro pode devolver tipos errados para .js
            fixos = {".js": "text/javascript", ".css": "text/css", ".html": "text/html",
                     ".svg": "image/svg+xml", ".png": "image/png", ".webmanifest": "application/manifest+json"}
            tipo = fixos.get(arquivo.suffix) or mimetypes.guess_type(arquivo.name)[0] \
                or "application/octet-stream"
            if tipo.startswith("text/") or tipo in ("application/javascript",):
                tipo += "; charset=utf-8"
            self._enviar(arquivo.read_bytes(), tipo)

    return Manipulador


def iniciar(host=None, porta=None, caminho_banco=None):
    estado = Estado(caminho_banco)
    servidor = ThreadingHTTPServer((host or config.HOST, config.PORTA if porta is None else porta),
                                   criar_manipulador(estado))
    return servidor, estado


def ip_na_rede_local():
    """Descobre o IP deste computador na rede Wi-Fi (nenhum pacote é enviado)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def principal(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Servidor do MenteAcessível SP")
    parser.add_argument("--celular", action="store_true",
                        help="aceita conexões de outros aparelhos da mesma rede (Wi-Fi)")
    parser.add_argument("--porta", type=int, default=None)
    args = parser.parse_args(argv)

    host = "0.0.0.0" if args.celular else None
    servidor, estado = iniciar(host, args.porta)
    porta = servidor.server_address[1]
    print(f"MenteAcessível SP rodando em http://127.0.0.1:{porta}")
    print(f"Painel analítico: http://127.0.0.1:{porta}/painel")
    if args.celular:
        ip = ip_na_rede_local()
        print("\n=== ACESSO PELO CELULAR (mesma rede Wi-Fi) ===")
        print(f"Digite no navegador do celular:  http://{ip or 'IP-DO-COMPUTADOR'}:{porta}")
        print("Se o Windows perguntar sobre o Firewall, permita em 'Redes privadas'.")
        print("O GPS do celular só funciona por link HTTPS (veja 'Usar no celular' no README).")
        print("==============================================\n")
    if not estado.pronto:
        print("\nATENÇÃO: o banco ainda está vazio. Em outro terminal rode:\n"
              "    python -m etl.coletar\n e depois reinicie o servidor.")
    else:
        print(f"{len(estado.unidades)} unidades em {len(estado.municipios)} municípios "
              f"(CNES {estado.metadados.get('competencia_cnes', '?')}).")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        servidor.server_close()


if __name__ == "__main__":
    principal()

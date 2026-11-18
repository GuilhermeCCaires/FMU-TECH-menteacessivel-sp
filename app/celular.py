"""Abre o MenteAcessível no celular com um único comando.

Uso:  python -m app.celular

1. Liga o servidor aceitando conexões da rede.
2. Cria um link HTTPS público e temporário com o Cloudflare Tunnel (gratuito,
   sem cadastro). Funciona no 4G, não precisa mexer no Firewall e libera o GPS
   do celular, que só funciona em sites https.
3. Abre no computador uma página com QR code: aponte a câmera do Android.

O link muda a cada execução e para de funcionar quando você fecha este programa.
Qualquer pessoa com o link consegue abrir o app: use para testes.
"""
import argparse
import ipaddress
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import config, servidor

PASTA_FERRAMENTAS = config.RAIZ / "ferramentas"
PADRAO_LINK = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
URL_DOWNLOAD = "https://github.com/cloudflare/cloudflared/releases/latest/download/{arquivo}"


# ----------------------------------------------------------- rede local (Wi-Fi)
def ips_na_rede_local():
    """IPs privados deste computador, do mais provável (Wi-Fi de casa) ao menos provável.

    No Windows é comum haver placas virtuais (WSL, Hyper-V, VirtualBox) com IPs
    172.x ou 192.168.56.x que o celular não alcança; elas vão para o fim da lista.
    """
    candidatos = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidatos.add(info[4][0])
    except OSError:
        pass
    ip_rota = servidor.ip_na_rede_local()
    if ip_rota:
        candidatos.add(ip_rota)

    def prioridade(ip):
        if ip.startswith("192.168.56."):        # VirtualBox
            return 4
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ipaddress.ip_address(ip) in ipaddress.ip_network("172.16.0.0/12"):
            return 3                              # muitas vezes WSL/Hyper-V/Docker
        return 2

    validos = []
    for ip in candidatos:
        try:
            endereco = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if endereco.is_private and not endereco.is_loopback and not endereco.is_link_local:
            validos.append(ip)
    return sorted(validos, key=lambda ip: (prioridade(ip), ip))


# ----------------------------------------------------------------- cloudflared
def _nome_arquivo_cloudflared():
    sistema = platform.system()
    maquina = platform.machine().lower()
    arm = maquina in ("arm64", "aarch64")
    if sistema == "Windows":
        return "cloudflared-windows-arm64.exe" if arm else "cloudflared-windows-amd64.exe"
    if sistema == "Linux":
        return "cloudflared-linux-arm64" if arm else "cloudflared-linux-amd64"
    return None  # macOS: instalar com "brew install cloudflared"


def encontrar_cloudflared():
    executavel = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    candidatos = [shutil.which("cloudflared"), PASTA_FERRAMENTAS / executavel]
    if os.name == "nt":
        for var in ("ProgramFiles(x86)", "ProgramFiles"):
            if os.environ.get(var):
                candidatos.append(Path(os.environ[var]) / "cloudflared" / "cloudflared.exe")
        if os.environ.get("LOCALAPPDATA"):
            candidatos.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe")
    for c in candidatos:
        if c and Path(c).is_file():
            return str(c)
    return None


def baixar_cloudflared():
    arquivo = _nome_arquivo_cloudflared()
    if not arquivo:
        raise RuntimeError("No macOS, instale com: brew install cloudflared")
    PASTA_FERRAMENTAS.mkdir(exist_ok=True)
    destino = PASTA_FERRAMENTAS / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
    temporario = destino.with_suffix(".baixando")
    url = URL_DOWNLOAD.format(arquivo=arquivo)
    print(f"Baixando o cloudflared do GitHub oficial da Cloudflare:\n  {url}")
    pedido = urllib.request.Request(url, headers={"User-Agent": "MenteAcessivel-SP"})
    with urllib.request.urlopen(pedido, timeout=120) as resposta, open(temporario, "wb") as saida:
        total = int(resposta.headers.get("Content-Length") or 0)
        baixado = 0
        while True:
            bloco = resposta.read(1024 * 256)
            if not bloco:
                break
            saida.write(bloco)
            baixado += len(bloco)
            if total:
                print(f"\r  {baixado * 100 // total}% de {total // (1024 * 1024)} MB", end="", flush=True)
    print()
    temporario.replace(destino)
    if os.name != "nt":
        destino.chmod(destino.stat().st_mode | stat.S_IEXEC)
    return str(destino)


def extrair_link(linha):
    achado = PADRAO_LINK.search(linha or "")
    return achado.group(0) if achado else None


def iniciar_tunel(executavel, porta, espera_max=60, log=None):
    """Roda o cloudflared e devolve (processo, link_https) quando o link aparecer."""
    processo = subprocess.Popen(
        [executavel, "tunnel", "--url", f"http://127.0.0.1:{porta}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1,
    )
    achado = {"link": None}
    pronto = threading.Event()

    def ler_saida():
        for linha in processo.stdout:  # continua lendo para o processo não travar
            if log is not None:
                log.append(linha.rstrip())
            if not achado["link"]:
                link = extrair_link(linha)
                if link:
                    achado["link"] = link
                    pronto.set()
        pronto.set()

    threading.Thread(target=ler_saida, daemon=True).start()
    pronto.wait(espera_max)
    if not achado["link"]:
        processo.terminate()
        raise RuntimeError("O cloudflared não gerou o link a tempo. Verifique a internet e tente de novo.")
    return processo, achado["link"]


# ------------------------------------------------------------------- programa
def principal(argv=None):
    parser = argparse.ArgumentParser(description="Abre o MenteAcessível no celular")
    parser.add_argument("--porta", type=int, default=config.PORTA)
    parser.add_argument("--sem-tunel", action="store_true", help="só a rede Wi-Fi local, sem link https")
    parser.add_argument("--sim", action="store_true", help="baixa o cloudflared sem perguntar")
    parser.add_argument("--nao-abrir", action="store_true", help="não abre o navegador do computador")
    args = parser.parse_args(argv)

    try:
        http, estado = servidor.iniciar("0.0.0.0", args.porta)
    except OSError:
        print(f"\nA porta {args.porta} já está em uso. Feche o outro servidor (Ctrl+C no terminal dele)\n"
              f"ou rode: python -m app.celular --porta 8001")
        return 1
    threading.Thread(target=http.serve_forever, daemon=True).start()
    porta = http.server_address[1]

    ips = ips_na_rede_local()
    acesso = servidor.ACESSO_CELULAR
    acesso.update(link_publico=None, links_locais=[f"http://{ip}:{porta}" for ip in ips],
                  situacao="Criando o link HTTPS...", erro=None)

    print("\n=== MenteAcessível SP no celular ===")
    if not estado.pronto:
        print("ATENÇÃO: o banco está vazio. Rode antes: python -m etl.coletar")
    if not args.nao_abrir:
        webbrowser.open(f"http://127.0.0.1:{porta}/celular")
        print(f"Abrimos no seu navegador a página com o QR code: http://127.0.0.1:{porta}/celular")

    tunel = None
    if not args.sem_tunel:
        try:
            exe = encontrar_cloudflared()
            if not exe:
                print("\nPara criar o link HTTPS é preciso o programa gratuito 'cloudflared' (cerca de 60 MB).")
                resposta = "s" if args.sim else input("Baixar agora do site oficial da Cloudflare? [S/n] ").strip().lower()
                if resposta not in ("", "s", "sim", "y", "yes"):
                    raise RuntimeError("Download recusado. Sem o link HTTPS, use a rede Wi-Fi local.")
                exe = baixar_cloudflared()
            print("Criando o link HTTPS (leva uns 10 segundos)...")
            tunel, link = iniciar_tunel(exe, porta)
            acesso.update(link_publico=link, situacao="Pronto")
            print("\nPRONTO! No celular Android, abra este endereço (ou escaneie o QR code):\n")
            print(f"    {link}\n")
            print("Se aparecer erro no celular, espere 20 segundos e recarregue: o link leva um tempinho para ativar.")
        except (RuntimeError, OSError, urllib.error.URLError) as erro:
            acesso.update(erro=str(erro), situacao="Sem link HTTPS")
            print(f"\nNão foi possível criar o link HTTPS: {erro}")

    if ips:
        print("\nAlternativa na mesma rede Wi-Fi (sem GPS, pois não é https):")
        for ip in ips:
            print(f"    http://{ip}:{porta}")
        print("Se não abrir, libere a porta no Firewall (PowerShell como administrador):")
        print(f'    New-NetFirewallRule -DisplayName "MenteAcessivel {porta}" -Direction Inbound '
              f"-Protocol TCP -LocalPort {porta} -Action Allow -Profile Any")

    print("\nDeixe esta janela aberta. Para encerrar: Ctrl+C")
    try:
        while True:
            time.sleep(1)
            if tunel and tunel.poll() is not None:
                print("\nO túnel do Cloudflare foi encerrado. Rode o comando de novo para um novo link.")
                acesso.update(link_publico=None, situacao="Túnel encerrado", erro="Rode python -m app.celular de novo")
                tunel = None
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        if tunel:
            tunel.terminate()
        http.shutdown()
        http.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(principal())

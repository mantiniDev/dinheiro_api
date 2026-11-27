"""
Painel de controle — servidor que roda no PC.

- Mostra dados do PC (CPU, RAM, disco, rede, bateria, processos).
- Recebe "pedidos de liberação" (de scripts ou de outros programas),
  envia notificação para o celular e espera você aprovar ou negar.
- Executa ações pré-cadastradas (ex.: bloquear tela) a partir do celular.

Rodar:  python servidor.py
"""

import asyncio
import html
import json
import platform
import secrets
import subprocess
import time
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PASTA = Path(__file__).parent
ARQ_CONFIG = PASTA / "config.json"


# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------
VERSAO_ACOES = 2  # suba este número quando o config.exemplo.json ganhar ações novas


def carregar_config() -> dict:
    exemplo = json.loads((PASTA / "config.exemplo.json").read_text(encoding="utf-8"))
    if not ARQ_CONFIG.exists():
        exemplo["token"] = secrets.token_urlsafe(24)
        exemplo["ntfy_topico"] = "painel-" + secrets.token_hex(6)
        exemplo["versao_acoes"] = VERSAO_ACOES
        ARQ_CONFIG.write_text(json.dumps(exemplo, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[painel] config.json criado em {ARQ_CONFIG}")
    config = json.loads(ARQ_CONFIG.read_text(encoding="utf-8"))

    # Quem já tinha um config.json antigo ganha as ações novas do exemplo
    # (as que a pessoa já tem, ou editou, ficam como estão).
    if config.get("versao_acoes", 1) < VERSAO_ACOES:
        antigas = config.get("acoes", {})
        novas = {k: antigas.get(k, v) for k, v in exemplo["acoes"].items()}
        novas.update({k: v for k, v in antigas.items() if k not in novas})
        config["acoes"] = novas
        config["versao_acoes"] = VERSAO_ACOES
        ARQ_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[painel] config.json atualizado com {len(novas) - len(antigas)} ações novas")
    return config


CONFIG = carregar_config()
TOKEN = CONFIG["token"]


def exigir_token(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    """Aceita 'Authorization: Bearer <token>' ou '?token=<token>'."""
    recebido = token
    if authorization and authorization.lower().startswith("bearer "):
        recebido = authorization[7:]
    if not recebido or not secrets.compare_digest(recebido, TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")


@asynccontextmanager
async def ciclo_de_vida(_app):
    psutil.cpu_percent(interval=None)  # primeira leitura "aquece" a medição
    tarefa = asyncio.create_task(vigiar())
    yield
    tarefa.cancel()


app = FastAPI(title="Painel de Controle", lifespan=ciclo_de_vida)


# --------------------------------------------------------------------------
# Notificações (ntfy.sh — app gratuito para Android)
# --------------------------------------------------------------------------
def enviar_ntfy(titulo: str, mensagem: str, acoes: list[dict] | None = None, prioridade: int = 3):
    topico = CONFIG.get("ntfy_topico")
    if not topico:
        return
    servidor = CONFIG.get("ntfy_servidor", "https://ntfy.sh").rstrip("/")
    corpo = {
        "topic": topico,
        "title": titulo,
        "message": mensagem,
        "priority": prioridade,
        "tags": ["computer"],
    }
    if acoes:
        corpo["actions"] = acoes
    req = urllib.request.Request(
        servidor,
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as erro:  # notificação é "melhor esforço"
        print(f"[painel] falha ao enviar ntfy: {erro}")


# --------------------------------------------------------------------------
# Dados do PC
# --------------------------------------------------------------------------
_rede_anterior = {"t": time.time(), "env": 0, "rec": 0}


def coletar_status() -> dict:
    mem = psutil.virtual_memory()
    try:
        disco = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
        disco_info = {"total_gb": round(disco.total / 1e9, 1), "usado_gb": round(disco.used / 1e9, 1), "pct": disco.percent}
    except Exception:
        disco_info = None

    # Velocidade de rede desde a última leitura
    rede = psutil.net_io_counters()
    agora = time.time()
    dt = max(agora - _rede_anterior["t"], 0.001)
    subida = (rede.bytes_sent - _rede_anterior["env"]) / dt if _rede_anterior["env"] else 0
    descida = (rede.bytes_recv - _rede_anterior["rec"]) / dt if _rede_anterior["rec"] else 0
    _rede_anterior.update(t=agora, env=rede.bytes_sent, rec=rede.bytes_recv)

    bateria = None
    try:
        b = psutil.sensors_battery()
        if b:
            bateria = {"pct": round(b.percent), "carregando": b.power_plugged}
    except Exception:
        pass

    temperatura = None
    try:
        temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
        leituras = [t.current for lista in temps.values() for t in lista if t.current]
        if leituras:
            temperatura = round(max(leituras))
    except Exception:
        pass

    processos = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            processos.append((p.info["memory_info"].rss, p.info["name"]))
        except Exception:
            continue
    processos.sort(reverse=True)

    return {
        "nome_pc": platform.node(),
        "sistema": f"{platform.system()} {platform.release()}",
        "ligado_ha_s": int(agora - psutil.boot_time()),
        "cpu_pct": psutil.cpu_percent(interval=None),
        "cpu_nucleos": psutil.cpu_count(),
        "ram": {"total_gb": round(mem.total / 1e9, 1), "usado_gb": round(mem.used / 1e9, 1), "pct": mem.percent},
        "disco": disco_info,
        "rede": {"subida_kbs": round(subida / 1024, 1), "descida_kbs": round(descida / 1024, 1)},
        "bateria": bateria,
        "temperatura_c": temperatura,
        "top_processos": [{"nome": n, "ram_mb": round(r / 1e6)} for r, n in processos[:15]],
    }


@app.get("/api/status", dependencies=[Depends(exigir_token)])
def status():
    return coletar_status()


# --------------------------------------------------------------------------
# Pedidos de liberação (aprovar / negar pelo celular)
# --------------------------------------------------------------------------
class NovoPedido(BaseModel):
    titulo: str
    detalhe: str = ""
    origem: str = "script"


PEDIDOS: dict[str, dict] = {}
EVENTOS: dict[str, asyncio.Event] = {}


@app.post("/api/pedidos", dependencies=[Depends(exigir_token)])
async def criar_pedido(novo: NovoPedido):
    pid = uuid.uuid4().hex[:8]
    pedido = {
        "id": pid,
        "titulo": novo.titulo,
        "detalhe": novo.detalhe,
        "origem": novo.origem,
        "estado": "pendente",  # pendente | aprovado | negado
        "criado_em": time.time(),
        "decidido_em": None,
    }
    PEDIDOS[pid] = pedido
    EVENTOS[pid] = asyncio.Event()

    url = CONFIG.get("url_publica", "").rstrip("/")
    acoes = None
    if url:
        auth = {"Authorization": f"Bearer {TOKEN}"}
        acoes = [
            {"action": "http", "label": "✅ Liberar", "url": f"{url}/api/pedidos/{pid}/aprovar", "method": "POST", "headers": auth, "clear": True},
            {"action": "http", "label": "❌ Negar", "url": f"{url}/api/pedidos/{pid}/negar", "method": "POST", "headers": auth, "clear": True},
            {"action": "view", "label": "Abrir painel", "url": f"{url}/"},
        ]
    await asyncio.to_thread(
        enviar_ntfy, f"🔐 Pedido: {novo.titulo}", novo.detalhe or f"Origem: {novo.origem}", acoes, 4
    )
    return pedido


@app.get("/api/pedidos", dependencies=[Depends(exigir_token)])
def listar_pedidos():
    return sorted(PEDIDOS.values(), key=lambda p: p["criado_em"], reverse=True)[:50]


def _decidir(pid: str, estado: str):
    pedido = PEDIDOS.get(pid)
    if not pedido:
        raise HTTPException(404, "Pedido não encontrado")
    if pedido["estado"] == "pendente":
        pedido["estado"] = estado
        pedido["decidido_em"] = time.time()
        EVENTOS[pid].set()
    return pedido


@app.post("/api/pedidos/{pid}/aprovar", dependencies=[Depends(exigir_token)])
def aprovar(pid: str):
    return _decidir(pid, "aprovado")


@app.post("/api/pedidos/{pid}/negar", dependencies=[Depends(exigir_token)])
def negar(pid: str):
    return _decidir(pid, "negado")


@app.get("/api/pedidos/{pid}/aguardar", dependencies=[Depends(exigir_token)])
async def aguardar(pid: str, timeout: int = Query(default=60, le=300)):
    """Fica esperando até o pedido ser decidido (ou o tempo acabar)."""
    if pid not in PEDIDOS:
        raise HTTPException(404, "Pedido não encontrado")
    try:
        await asyncio.wait_for(EVENTOS[pid].wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return PEDIDOS[pid]


# --------------------------------------------------------------------------
# Ações pré-cadastradas (só as que estão no config.json podem rodar)
# --------------------------------------------------------------------------
@app.get("/api/acoes", dependencies=[Depends(exigir_token)])
def listar_acoes():
    return [{"id": k, "nome": v.get("nome", k), "confirmar": v.get("confirmar", False)}
            for k, v in CONFIG.get("acoes", {}).items()]


# Teclas virtuais do Windows (https://learn.microsoft.com/windows/win32/inputdev/virtual-key-codes)
TECLAS = {
    "volume_mudo": 0xAD, "volume_menos": 0xAE, "volume_mais": 0xAF,
    "proxima": 0xB0, "anterior": 0xB1, "parar": 0xB2, "play_pausa": 0xB3,
    "win": 0x5B, "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "tab": 0x09, "esc": 0x1B,
    "enter": 0x0D, "espaco": 0x20, "printscreen": 0x2C, "delete": 0x2E,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}


def apertar_teclas(nomes: list[str]):
    """Aperta as teclas juntas (ex.: ["win", "shift", "s"]) e solta na ordem inversa."""
    if platform.system() != "Windows":
        raise RuntimeError("Atalhos de teclado só funcionam no Windows")
    import ctypes

    codigos = []
    for nome in nomes:
        nome = nome.lower()
        if nome in TECLAS:
            codigos.append(TECLAS[nome])
        elif len(nome) == 1 and nome.isalnum():
            codigos.append(ord(nome.upper()))
        else:
            raise ValueError(f"Tecla desconhecida: {nome}")
    teclado = ctypes.windll.user32
    SOLTAR, ESTENDIDA = 0x0002, 0x0001
    estendida = lambda c: ESTENDIDA if (c >= 0xA6 or c in (0x5B, 0x2E)) else 0
    for c in codigos:
        teclado.keybd_event(c, 0, estendida(c), 0)
        time.sleep(0.02)
    for c in reversed(codigos):
        teclado.keybd_event(c, 0, estendida(c) | SOLTAR, 0)
        time.sleep(0.02)


@app.post("/api/acoes/{aid}", dependencies=[Depends(exigir_token)])
def executar_acao(aid: str):
    acao = CONFIG.get("acoes", {}).get(aid)
    if not acao:
        raise HTTPException(404, "Ação não cadastrada")
    try:
        if "teclas" in acao:
            apertar_teclas(acao["teclas"])
            return {"ok": True, "codigo": 0, "saida": ""}
        r = subprocess.run(acao["comando"], capture_output=True, text=True, timeout=30)
        return {"ok": r.returncode == 0, "codigo": r.returncode, "saida": (r.stdout + r.stderr)[-500:]}
    except Exception as erro:
        return {"ok": False, "codigo": -1, "saida": str(erro)}


# --------------------------------------------------------------------------
# Alertas automáticos (CPU/RAM/disco altos)
# --------------------------------------------------------------------------
async def vigiar():
    limites = CONFIG.get("alertas", {})
    ultimo_alerta: dict[str, float] = {}
    while True:
        await asyncio.sleep(30)
        try:
            s = await asyncio.to_thread(coletar_status)
        except Exception:
            continue
        checagens = {
            "cpu": (s["cpu_pct"], limites.get("cpu_pct")),
            "ram": (s["ram"]["pct"], limites.get("ram_pct")),
            "disco": (s["disco"]["pct"] if s["disco"] else 0, limites.get("disco_pct")),
        }
        for nome, (valor, limite) in checagens.items():
            if limite and valor >= limite and time.time() - ultimo_alerta.get(nome, 0) > 900:
                ultimo_alerta[nome] = time.time()
                await asyncio.to_thread(
                    enviar_ntfy, f"⚠️ {nome.upper()} alto em {s['nome_pc']}", f"{nome}: {valor}% (limite {limite}%)", None, 4
                )




# --------------------------------------------------------------------------
# Página do painel (PWA)
# --------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")


def _links() -> list[tuple[bool, str, str]]:
    """(é_bluetooth, nome_da_conexão, ip) de cada conexão de rede do PC."""
    import socket

    links = []
    for nome, enderecos in psutil.net_if_addrs().items():
        for e in enderecos:
            if e.family == socket.AF_INET and not e.address.startswith(("127.", "169.254.")):
                bt = any(p in nome.lower() for p in ("bluetooth", "bnep", "pan"))
                links.append((bt, nome, e.address))
    return sorted(links, reverse=True)  # Bluetooth primeiro


@app.get("/qr", response_class=HTMLResponse)
def pagina_qr(request: Request):
    """QR code com o link já com token. Só abre no próprio PC."""
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Abra esta página no próprio PC (http://localhost:8765/qr)")
    porta = int(CONFIG.get("porta", 8765))
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return "<p>Instale o gerador de QR code: <code>pip install qrcode</code> e reinicie o painel.</p>"
    blocos = []
    for bt, nome, ip in _links():
        url = f"http://{ip}:{porta}/?token={TOKEN}"
        svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12).to_string(encoding="unicode")
        blocos.append(
            f"<div class='b'><h2>{'📶 Bluetooth' if bt else '🌐 ' + html.escape(nome)}</h2>"
            f"<div class='qr'>{svg}</div><code>{html.escape(url)}</code></div>"
        )
    corpo = "".join(blocos) or "<p>Nenhuma conexão de rede encontrada.</p>"
    return (
        "<!DOCTYPE html><html lang='pt-BR'><meta charset='utf-8'><title>Conectar celular</title>"
        "<style>body{font-family:system-ui;background:#0f1115;color:#e7e9ee;text-align:center;padding:20px}"
        ".b{display:inline-block;margin:12px;padding:16px;background:#181b22;border-radius:16px;vertical-align:top}"
        ".qr{background:#fff;padding:12px;border-radius:12px;display:inline-block}.qr svg{width:260px;height:260px}"
        "code{display:block;margin-top:10px;font-size:12px;color:#8b92a1;word-break:break-all;max-width:300px}</style>"
        "<h1>Aponte a câmera do celular</h1><p>O celular precisa estar na mesma rede (Wi-Fi ou Bluetooth).</p>"
        f"{corpo}</html>"
    )


@app.get("/")
def pagina():
    return FileResponse(PASTA / "static" / "index.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse(PASTA / "static" / "sw.js", media_type="application/javascript")


if __name__ == "__main__":
    import socket

    import uvicorn

    porta = int(CONFIG.get("porta", 8765))

    links = _links()

    print("\n=== Painel de Controle ===")
    if not links:
        print(f"No celular, abra:  http://IP-DO-PC:{porta}/?token={TOKEN}")
    for bt, nome, ip in links:
        marca = "  <- Bluetooth" if bt else ""
        print(f"[{nome}]  http://{ip}:{porta}/?token={TOKEN}{marca}")
    print(f"QR code p/ celular: abra http://localhost:{porta}/qr no navegador do PC")
    print(f"Tópico ntfy:       {CONFIG.get('ntfy_topico')}")
    print("==========================\n")
    uvicorn.run(app, host="0.0.0.0", port=porta, log_level="warning")

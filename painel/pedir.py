"""
Pede liberação pelo celular e espera a resposta.

Uso:
    python pedir.py "Liberar internet do PC das crianças" "Pedido às 21h"

Código de saída: 0 = liberado, 1 = negado, 2 = sem resposta (tempo esgotado).
Assim dá para usar em outros scripts:
    python pedir.py "Rodar backup" && rodar_backup.bat
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
BASE = f"http://127.0.0.1:{CONFIG.get('porta', 8765)}"
CABECALHO = {"Authorization": f"Bearer {CONFIG['token']}", "Content-Type": "application/json"}


def chamar(metodo: str, caminho: str, corpo: dict | None = None, timeout: int = 30) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(BASE + caminho, data=dados, headers=CABECALHO, method=metodo)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(64)
    titulo = sys.argv[1]
    detalhe = sys.argv[2] if len(sys.argv) > 2 else ""
    espera_max = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    pedido = chamar("POST", "/api/pedidos", {"titulo": titulo, "detalhe": detalhe, "origem": "pedir.py"})
    print(f"Pedido {pedido['id']} enviado. Aguardando resposta no celular...")

    limite = time.time() + espera_max
    while time.time() < limite:
        restante = int(min(60, limite - time.time()))
        if restante <= 0:
            break
        pedido = chamar("GET", f"/api/pedidos/{pedido['id']}/aguardar?timeout={restante}", timeout=restante + 10)
        if pedido["estado"] == "aprovado":
            print("✅ Liberado!")
            sys.exit(0)
        if pedido["estado"] == "negado":
            print("❌ Negado.")
            sys.exit(1)
    print("⏱️ Sem resposta.")
    sys.exit(2)


if __name__ == "__main__":
    main()

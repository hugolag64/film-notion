import socket
import sys
import uvicorn

from server.nas_server import app

PORT = 8000
HOST = "0.0.0.0"  # écoute localhost + Tailscale + LAN


def port_in_use(port: int) -> bool:
    """
    Vérifie si le port est déjà utilisé en local
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    if port_in_use(PORT):
        print(f"⚠️ Serveur déjà lancé sur le port {PORT}, arrêt.")
        sys.exit(0)

    print("🚀 Serveur Film Notion démarré")
    print(f"📡 Écoute sur {HOST}:{PORT}")

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="warning"
    )

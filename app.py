import sys
import threading
import traceback

from scripts.sync_nas_to_notion import sync_nas_to_notion
from ui.main_window import MovieUpdaterWindow


def run_nas_sync():
    """
    Lance la synchronisation NAS → Notion
    dans un thread séparé pour ne pas bloquer l'UI
    """
    print("🔄 Sync NAS → Notion au démarrage de l'application")
    try:
        sync_nas_to_notion()
        print("✅ Sync NAS terminée")
    except Exception:
        print("⚠️ Erreur lors de la sync NAS")
        traceback.print_exc()


if __name__ == "__main__":
    auto = "--auto" in sys.argv

    # =====================
    # Sync NAS → Notion (BACKGROUND)
    # =====================
    threading.Thread(
        target=run_nas_sync,
        daemon=True
    ).start()

    # =====================
    # Lancement UI
    # =====================
    app = MovieUpdaterWindow(auto_mode=auto)
    app.mainloop()

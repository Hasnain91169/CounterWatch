"""
Frozen-app entry point for the OW Strategiser counter-pick server.

Used by PyInstaller to build a standalone .exe. When frozen, the working
data/ and web/ folders live next to the .exe (not inside the bundle), so
your edits to preferences.json / config.json persist normally.

Run directly for testing:  python owstrat_launcher.py
"""

import sys
import threading
import time
import webbrowser
from pathlib import Path

# Base dir = folder containing the .exe when frozen, else this script's folder.
if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).parent
else:
    BASE = Path(__file__).parent

import engine
import server

# Point both modules at the external data/ and web/ folders next to the exe.
engine.DATA = BASE / "data"
server.ROOT = BASE
server.DATA = BASE / "data"
server.WEB = BASE / "web"
server.HERO_ASSETS = server.WEB / "assets" / "heroes"

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def _open_browser_when_ready():
    time.sleep(1.5)
    webbrowser.open(URL)


def main():
    if not server.WEB.exists():
        print(f"Missing web/ folder next to the app (looked in {server.WEB}).")
        input("Press Enter to exit...")
        return

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    # server.main() parses sys.argv; keep only host/port defaults.
    sys.argv = [sys.argv[0], "--host", HOST, "--port", str(PORT)]
    server.main()


if __name__ == "__main__":
    main()

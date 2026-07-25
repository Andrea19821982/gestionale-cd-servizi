"""Eseguibile server: avvia FastAPI in ascolto sulla rete locale, con
un'icona nella system tray per avviarlo/fermarlo senza dover tenere aperta
una finestra di console. Pensato per essere impacchettato con PyInstaller
come CalendarioTurni-Server.exe e lasciato acceso su un PC dell'ufficio.

Uso in sviluppo:
    python server_app.py
"""

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from app.paths import cartella_dati, cartella_risorse

# Impacchettato con console=False (niente finestra di console): sys.stdout
# e sys.stderr sono None, e uvicorn va in crash appena prova a configurare
# il logging (controlla stdout.isatty()). Li rediriggiamo su un file di
# log accanto all'eseguibile, prima di importare uvicorn/pystray, così
# anche eventuali altri controlli su stdout/stderr durante l'import non
# falliscono allo stesso modo.
if sys.stdout is None or sys.stderr is None:
    _log = open(cartella_dati() / "log.txt", "a", encoding="utf-8", buffering=1)
    sys.stdout = _log
    sys.stderr = _log

import pystray
import uvicorn
from PIL import Image

from app.database import init_db

PORTA = 8420


def _server_gia_in_ascolto() -> bool:
    """True se qualcosa è già in ascolto su localhost:PORTA: prima di
    avviare un secondo server sulla stessa porta (che fallirebbe subito nel
    bind e lascerebbe un'icona fantasma nella system tray, senza aprire
    nulla — vedi main() sotto), controlla se il doppio clic sul
    collegamento è arrivato mentre il server è già acceso da prima."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", PORTA))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _attendi_e_apri_browser() -> None:
    """Apre il browser sul calendario appena il server è pronto a
    rispondere: uvicorn impiega qualche secondo ad avviarsi, aprire subito
    rischierebbe di mostrare "impossibile raggiungere il sito" invece del
    calendario. Gira in un thread separato per non bloccare l'avvio
    dell'icona nella system tray."""
    scadenza = time.monotonic() + 15
    while time.monotonic() < scadenza:
        if _server_gia_in_ascolto():
            webbrowser.open(f"http://localhost:{PORTA}")
            return
        time.sleep(0.3)


def indirizzo_lan() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class ThreadServer(threading.Thread):
    """Esegue uvicorn in un thread separato, così il thread principale resta
    libero per il loop dell'icona nella system tray."""

    def __init__(self):
        super().__init__(daemon=True)
        from app.main import app  # importato qui: solo dopo init_db()

        configurazione = uvicorn.Config(app, host="0.0.0.0", port=PORTA, log_level="info")
        self.server = uvicorn.Server(configurazione)

    def run(self):
        self.server.run()

    def ferma(self):
        self.server.should_exit = True


def _carica_icona() -> Image.Image:
    percorso_icona = cartella_risorse() / "assets" / "icon.ico"
    if percorso_icona.exists():
        return Image.open(percorso_icona)
    # Icona di riserva, nel caso il file non sia stato incluso nel pacchetto.
    return Image.new("RGB", (64, 64), "#2563eb")


def _scrivi_indirizzo_su_file(ip: str) -> None:
    """Scrive l'indirizzo accanto all'eseguibile, in un file di testo
    semplice: comodo da aprire e copiare per comunicarlo ai colleghi senza
    dover leggere la console o aprire il menu della system tray."""
    try:
        percorso = cartella_dati() / "indirizzo_server.txt"
        percorso.write_text(
            "Indirizzo del server Calendario Turni (da dare ai colleghi):\n"
            f"{ip}:{PORTA}\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # non blocca l'avvio del server per un problema di scrittura file


def main():
    if _server_gia_in_ascolto():
        # Il server è già acceso su questo PC (avviato in precedenza e
        # lasciato attivo, come da istruzioni di installa_server.ps1):
        # riavviare l'eseguibile non deve tentare una seconda istanza sulla
        # stessa porta (fallirebbe subito e lascerebbe un'icona fantasma
        # nella system tray, senza aprire nulla — questo è esattamente
        # perché prima il doppio clic sul collegamento sembrava non fare
        # niente). Basta aprire il browser su quello già in esecuzione.
        webbrowser.open(f"http://localhost:{PORTA}")
        return

    init_db()
    server_thread = ThreadServer()
    server_thread.start()
    threading.Thread(target=_attendi_e_apri_browser, daemon=True).start()

    ip = indirizzo_lan()
    _scrivi_indirizzo_su_file(ip)

    def apri_nel_browser(icon=None, item=None):
        webbrowser.open(f"http://localhost:{PORTA}")

    def ferma_ed_esci(icon, item):
        server_thread.ferma()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(f"Server attivo — {ip}:{PORTA}", None, enabled=False),
        pystray.MenuItem("Apri nel browser", apri_nel_browser, default=True),
        pystray.MenuItem("Ferma il server ed esci", ferma_ed_esci),
    )
    icona = pystray.Icon("CalendarioTurni", _carica_icona(), "Calendario Turni — Server", menu)

    def mostra_avviso_iniziale(icon: pystray.Icon) -> None:
        # Su alcuni backend l'icona deve già essere visibile prima di poter
        # mostrare una notifica: per questo va fatto qui dentro (chiamato da
        # icona.run(setup=...)), non prima di avviare il loop dell'icona.
        icon.visible = True
        if icon.HAS_NOTIFICATION:
            icon.notify(f"Indirizzo per i colleghi: {ip}:{PORTA}", "Calendario Turni — server avviato")

    print("=" * 60)
    print("Calendario Turni - server avviato")
    print(f"Da questo PC:        http://localhost:{PORTA}")
    print(f"Dagli altri PC:      http://{ip}:{PORTA}")
    print("Icona nella system tray per fermarlo. Chiudendo questa finestra")
    print("il server si ferma comunque.")
    print("=" * 60)

    icona.run(setup=mostra_avviso_iniziale)


if __name__ == "__main__":
    main()

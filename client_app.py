"""Eseguibile client: apre una finestra simile a un programma nativo,
puntata all'indirizzo del server. Al primo avvio chiede l'indirizzo del
server e lo salva in un file di configurazione locale accanto
all'eseguibile. Pensato per essere impacchettato con PyInstaller come
CalendarioTurni.exe, uno per ogni PC dell'ufficio.

Uso in sviluppo:
    python client_app.py

Per rifare la configurazione dell'indirizzo del server (es. il server è
cambiato PC), rilanciare con l'opzione --configura.
"""

import json
import sys
from pathlib import Path

import webview

NOME_FILE_CONFIG = "client_config.json"
TITOLO_FINESTRA = "Calendario Turni"


def _cartella_eseguibile() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _percorso_config() -> Path:
    return _cartella_eseguibile() / NOME_FILE_CONFIG


def leggi_indirizzo_server() -> str | None:
    percorso = _percorso_config()
    if not percorso.exists():
        return None
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dati.get("indirizzo_server")


def salva_indirizzo_server(indirizzo: str) -> None:
    _percorso_config().write_text(
        json.dumps({"indirizzo_server": indirizzo}), encoding="utf-8"
    )


def _normalizza_indirizzo(indirizzo: str) -> str:
    indirizzo = indirizzo.strip()
    if not indirizzo.startswith("http://") and not indirizzo.startswith("https://"):
        indirizzo = f"http://{indirizzo}"
    return indirizzo


HTML_CONFIGURAZIONE = """
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Configurazione — Calendario Turni</title>
<style>
  body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; background: #f5f6f8; margin: 0; }
  .box { max-width: 360px; margin: 15vh auto; background: white; padding: 2rem; border-radius: 8px; border: 1px solid #dde1e6; }
  h1 { font-size: 1.2rem; margin-top: 0; }
  input { width: 100%; padding: 0.5rem; margin: 0.5rem 0 1rem; border: 1px solid #dde1e6; border-radius: 4px; box-sizing: border-box; font-size: 1rem; }
  button { width: 100%; padding: 0.5rem; background: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 1rem; }
  p { color: #6b7280; font-size: 0.85rem; }
</style>
</head>
<body>
  <div class="box">
    <h1>Calendario Turni</h1>
    <p>Indirizzo del PC che fa da server (chiedilo a chi lo gestisce), ad esempio 192.168.1.50:8420.</p>
    <input type="text" id="indirizzo" placeholder="192.168.1.50:8420" autofocus>
    <button onclick="conferma()">Connetti</button>
  </div>
  <script>
    function conferma() {
        const valore = document.getElementById('indirizzo').value.trim();
        if (valore) { window.pywebview.api.salva_e_connetti(valore); }
    }
    document.getElementById('indirizzo').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') conferma();
    });
  </script>
</body>
</html>
"""


class ApiClient:
    def salva_e_connetti(self, indirizzo: str) -> None:
        indirizzo = _normalizza_indirizzo(indirizzo)
        salva_indirizzo_server(indirizzo)
        webview.windows[0].load_url(indirizzo)


def main():
    forza_configurazione = "--configura" in sys.argv
    indirizzo_salvato = None if forza_configurazione else leggi_indirizzo_server()

    webview.create_window(
        TITOLO_FINESTRA,
        url=indirizzo_salvato if indirizzo_salvato else None,
        html=None if indirizzo_salvato else HTML_CONFIGURAZIONE,
        js_api=ApiClient(),
        width=1400,
        height=900,
    )
    webview.start()


if __name__ == "__main__":
    main()

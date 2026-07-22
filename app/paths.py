"""Percorsi consapevoli della modalità di esecuzione: script Python in
sviluppo oppure eseguibile impacchettato con PyInstaller.

Una volta impacchettato, il codice gira da una cartella temporanea di
estrazione (sys._MEIPASS): lì dentro deve stare solo cosa è di sola lettura
(template, static). Il database va scritto accanto all'eseguibile vero e
proprio, altrimenti sparirebbe ad ogni riavvio.
"""

import sys
from pathlib import Path


def _impacchettato() -> bool:
    return bool(getattr(sys, "frozen", False))


def cartella_dati() -> Path:
    """Cartella scrivibile: accanto all'eseguibile se impacchettato, radice
    del progetto in sviluppo."""
    if _impacchettato():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def cartella_risorse() -> Path:
    """Cartella di sola lettura per template/static: dentro il bundle
    PyInstaller se impacchettato, radice del progetto in sviluppo."""
    if _impacchettato():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

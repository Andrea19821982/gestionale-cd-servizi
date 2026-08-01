"""La versione è scritta in quattro posti che non possono leggersi a
vicenda (app/versione.py per il programma, installer.iss per Inno Setup,
versione_client.txt e versione_server.txt per PyInstaller). Questi test
sono l'unica cosa che impedisce che divergano: senza, prima o poi si
aggiorna l'installer e non il resto, e la pagina Stato del programma
dichiara una versione diversa da quella davvero installata.
"""

import re
from pathlib import Path

from app.versione import VERSIONE

RADICE = Path(__file__).resolve().parent.parent


def test_la_versione_e_quella_dell_installer():
    testo = (RADICE / "installer.iss").read_text(encoding="utf-8")
    trovata = re.search(r'#define Versione "([\d.]+)"', testo)
    assert trovata, "non trovo #define Versione in installer.iss"
    assert trovata.group(1) == VERSIONE


def test_la_versione_e_quella_incorporata_negli_eseguibili():
    attesa = tuple(int(n) for n in VERSIONE.split("."))
    for nome in ("versione_client.txt", "versione_server.txt"):
        testo = (RADICE / nome).read_text(encoding="utf-8")

        trovata = re.search(r"filevers=\((\d+), (\d+), (\d+), \d+\)", testo)
        assert trovata, f"non trovo filevers in {nome}"
        assert tuple(int(n) for n in trovata.groups()) == attesa, nome

        assert f"'{VERSIONE}.0'" in testo, f"FileVersion/ProductVersion disallineati in {nome}"

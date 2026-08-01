"""Percorsi dei dati e recupero da installazioni precedenti (app/paths.py).

Questi test coprono il caso che, se sbagliato, si nota solo quando è già
troppo tardi: il server che riparte con un database vuoto dopo un
aggiornamento, mentre i turni di tutti sono ancora sul disco in un'altra
cartella. Vale la pena tenerli anche se il codice è breve.
"""

import sqlite3
import sys

import pytest

from app import paths


def _crea_db(percorso, contenuto):
    """Un turni.db vero, non un file di testo: il recupero ora lo copia con
    l'API di backup di sqlite3 (vedi paths._copia_database), quindi un
    segnaposto di testo non sarebbe più rappresentativo."""
    con = sqlite3.connect(percorso)
    try:
        con.execute("CREATE TABLE prova (valore TEXT)")
        con.execute("INSERT INTO prova (valore) VALUES (?)", (contenuto,))
        con.commit()
    finally:
        con.close()


def _leggi_db(percorso):
    con = sqlite3.connect(percorso)
    try:
        return con.execute("SELECT valore FROM prova").fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def finto_eseguibile(tmp_path, monkeypatch):
    """Simula l'eseguibile impacchettato con PyInstaller: sys.frozen attivo,
    sys.executable in una cartella finta e LOCALAPPDATA sotto tmp_path, così
    i test non toccano i dati veri sul PC.

    Restituisce una funzione per (ri)calcolare la cartella dati svuotando la
    cache: cartella_dati() è @lru_cache, altrimenti il primo test
    congelerebbe il risultato per tutti gli altri.
    """
    localappdata = tmp_path / "LocalAppData"
    localappdata.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    def imposta_cartella_programma(percorso_relativo: str):
        cartella = tmp_path / percorso_relativo
        cartella.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sys, "executable", str(cartella / "CalendarioTurni-Server.exe"))
        return cartella

    paths.cartella_dati.cache_clear()
    paths.cartella_dati_client.cache_clear()
    yield localappdata, imposta_cartella_programma
    paths.cartella_dati.cache_clear()
    paths.cartella_dati_client.cache_clear()


def test_in_sviluppo_i_dati_restano_nella_radice_del_progetto():
    """Senza sys.frozen niente deve cambiare: chi lavora sul codice continua
    a trovare turni.db nella cartella del progetto."""
    radice = paths.cartella_dati()
    assert (radice / "app" / "paths.py").exists()


def test_i_dati_stanno_fuori_dalla_cartella_del_programma(finto_eseguibile):
    localappdata, imposta_cartella_programma = finto_eseguibile
    cartella_programma = imposta_cartella_programma("Programs/Gestionale CD-Servizi/Server")

    dati = paths.cartella_dati()

    assert dati == localappdata / "CD-Servizi" / "CalendarioTurni-Server"
    assert cartella_programma not in dati.parents
    assert dati.is_dir()


def test_client_e_server_usano_cartelle_separate(finto_eseguibile):
    localappdata, imposta_cartella_programma = finto_eseguibile
    imposta_cartella_programma("Programs/Gestionale CD-Servizi/Server")

    assert paths.cartella_dati() != paths.cartella_dati_client()
    assert paths.cartella_dati_client() == localappdata / "CD-Servizi" / "CalendarioTurni"


def test_recupera_i_dati_scritti_accanto_all_eseguibile(finto_eseguibile):
    """Versioni vecchie avviate dalla cartella del programma."""
    _, imposta_cartella_programma = finto_eseguibile
    vecchia = imposta_cartella_programma("Programs/CalendarioTurni-Server")
    _crea_db(vecchia / "turni.db", "turni")
    (vecchia / "secret_key.txt").write_text("chiave", encoding="utf-8")
    (vecchia / "allegati").mkdir()
    (vecchia / "allegati" / "certificato.pdf").write_text("pdf", encoding="utf-8")

    dati = paths.cartella_dati()

    assert _leggi_db(dati / "turni.db") == "turni"
    assert (dati / "secret_key.txt").read_text(encoding="utf-8") == "chiave"
    assert (dati / "allegati" / "certificato.pdf").read_text(encoding="utf-8") == "pdf"


def test_recupera_i_dati_dalla_vecchia_cartella_di_installazione(finto_eseguibile):
    """Il caso dell'aggiornamento vero: il nuovo eseguibile è in un'altra
    cartella, i dati sono dove li mettevano gli script installa_*.ps1."""
    localappdata, imposta_cartella_programma = finto_eseguibile
    vecchia = localappdata / "Programs" / "CalendarioTurni-Server"
    vecchia.mkdir(parents=True)
    _crea_db(vecchia / "turni.db", "turni di tutti")
    (vecchia / "backup").mkdir()
    (vecchia / "backup" / "turni_2026-07-01.db").write_text("backup", encoding="utf-8")
    # Il nuovo eseguibile sta altrove e la sua cartella non contiene dati.
    imposta_cartella_programma("Programs/Gestionale CD-Servizi/Server")

    dati = paths.cartella_dati()

    assert _leggi_db(dati / "turni.db") == "turni di tutti"
    assert (dati / "backup" / "turni_2026-07-01.db").exists()


def test_gli_originali_non_vengono_cancellati(finto_eseguibile):
    """Il recupero copia, non sposta: se qualcosa va storto i dati veri
    devono restare dove erano."""
    localappdata, imposta_cartella_programma = finto_eseguibile
    vecchia = localappdata / "Programs" / "CalendarioTurni-Server"
    vecchia.mkdir(parents=True)
    _crea_db(vecchia / "turni.db", "turni")
    imposta_cartella_programma("Programs/Gestionale CD-Servizi/Server")

    paths.cartella_dati()

    assert _leggi_db(vecchia / "turni.db") == "turni"


def test_il_database_in_uso_non_viene_sovrascritto_da_una_copia_vecchia(finto_eseguibile):
    """Al secondo avvio il recupero non deve rifarsi: sovrascriverebbe il
    database aggiornato con quello rimasto nella vecchia cartella."""
    localappdata, imposta_cartella_programma = finto_eseguibile
    vecchia = localappdata / "Programs" / "CalendarioTurni-Server"
    vecchia.mkdir(parents=True)
    _crea_db(vecchia / "turni.db", "vecchio")
    imposta_cartella_programma("Programs/Gestionale CD-Servizi/Server")

    dati = paths.cartella_dati()
    (dati / "turni.db").unlink()
    _crea_db(dati / "turni.db", "aggiornato")
    paths.cartella_dati.cache_clear()

    assert _leggi_db(paths.cartella_dati() / "turni.db") == "aggiornato"


def test_installazione_pulita_non_inventa_nessun_file(finto_eseguibile):
    _, imposta_cartella_programma = finto_eseguibile
    imposta_cartella_programma("Programs/Gestionale CD-Servizi/Server")

    dati = paths.cartella_dati()

    assert dati.is_dir()
    assert not (dati / "turni.db").exists()

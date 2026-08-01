"""Recupero dei dati dalle installazioni precedenti (app/paths.py).

Questi test nascono da una perdita di dati vera, capitata due volte in
produzione: il database sano si ritrovava in silenzio il contenuto di una
vecchia installazione, senza nessun errore e superando pure
PRAGMA integrity_check, e in alcuni casi finiva corrotto.
"""

import sqlite3

from app.paths import _DATI_SERVER_DA_MIGRARE, _migra_dati


def _crea_database(percorso, valori, lascia_wal_aperto=False):
    """Crea un database in modalità WAL (la stessa usata dal programma,
    vedi app/database.py). Con lascia_wal_aperto=True il -wal resta sul
    disco senza essere riassorbito, com'è normale dopo una chiusura brusca
    del programma."""
    percorso.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(percorso)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE dati (id INTEGER PRIMARY KEY, valore TEXT)")
    for v in valori:
        con.execute("INSERT INTO dati (valore) VALUES (?)", (v,))
    con.commit()
    if lascia_wal_aperto:
        return con  # il chiamante lo tiene aperto: il -wal resta sul disco
    con.close()
    return None


def _valori(percorso):
    con = sqlite3.connect(percorso)
    try:
        return [r[0] for r in con.execute("SELECT valore FROM dati ORDER BY id")]
    finally:
        con.close()


def test_il_wal_della_vecchia_installazione_non_viene_innestato_sul_database_buono(tmp_path):
    """Il caso che ha causato la perdita di dati: la destinazione ha già il
    suo turni.db (che va giustamente saltato) ma nessun -wal, perché il
    programma era stato chiuso regolarmente. Il -wal della vecchia
    installazione NON deve finirle accanto: SQLite lo applicherebbe come se
    fosse suo, sostituendo il contenuto del database sano."""
    destinazione = tmp_path / "dati"
    vecchia = tmp_path / "vecchia_installazione"

    _crea_database(destinazione / "turni.db", [f"buono-{i}" for i in range(20)])
    con_vecchio = _crea_database(vecchia / "turni.db", ["vecchio-1"], lascia_wal_aperto=True)
    for i in range(200):
        con_vecchio.execute("INSERT INTO dati (valore) VALUES (?)", (f"vecchio-extra-{i}",))
    con_vecchio.commit()
    assert (vecchia / "turni.db-wal").exists(), "il presupposto del test: la vecchia installazione ha un -wal"

    _migra_dati(destinazione, _DATI_SERVER_DA_MIGRARE, [vecchia])

    assert not (destinazione / "turni.db-wal").exists()
    assert not (destinazione / "turni.db-shm").exists()
    assert _valori(destinazione / "turni.db") == [f"buono-{i}" for i in range(20)]
    con_vecchio.close()


def test_recupero_da_installazione_precedente_include_le_modifiche_nel_wal(tmp_path):
    """Rinunciare a copiare il -wal non deve far perdere le ultime
    modifiche: quando la destinazione è davvero vuota, il database va
    recuperato per intero, comprese le transazioni che stanno ancora solo
    nel -wal della vecchia installazione."""
    destinazione = tmp_path / "dati"
    destinazione.mkdir()
    vecchia = tmp_path / "vecchia_installazione"

    con_vecchio = _crea_database(vecchia / "turni.db", ["consolidato"], lascia_wal_aperto=True)
    con_vecchio.execute("INSERT INTO dati (valore) VALUES ('solo-nel-wal')")
    con_vecchio.commit()

    _migra_dati(destinazione, _DATI_SERVER_DA_MIGRARE, [vecchia])

    assert _valori(destinazione / "turni.db") == ["consolidato", "solo-nel-wal"]
    con_vecchio.close()


def test_il_marcatore_impedisce_una_seconda_migrazione(tmp_path):
    destinazione = tmp_path / "dati"
    destinazione.mkdir()  # la crea _cartella_dati_utente prima di chiamare _migra_dati
    vecchia = tmp_path / "vecchia_installazione"
    _crea_database(vecchia / "turni.db", ["vecchio"])

    _migra_dati(destinazione, _DATI_SERVER_DA_MIGRARE, [vecchia])
    assert _valori(destinazione / "turni.db") == ["vecchio"]

    # Il database viene poi usato e modificato normalmente dal programma.
    con = sqlite3.connect(destinazione / "turni.db")
    con.execute("INSERT INTO dati (valore) VALUES ('lavoro-vero')")
    con.commit()
    con.close()

    _migra_dati(destinazione, _DATI_SERVER_DA_MIGRARE, [vecchia])
    assert _valori(destinazione / "turni.db") == ["vecchio", "lavoro-vero"]


def test_wal_e_shm_non_sono_piu_nella_lista_da_migrare():
    """Guardia esplicita: rimetterli in lista reintrodurrebbe la perdita di
    dati, e da soli sembrano innocui."""
    assert "turni.db-wal" not in _DATI_SERVER_DA_MIGRARE
    assert "turni.db-shm" not in _DATI_SERVER_DA_MIGRARE

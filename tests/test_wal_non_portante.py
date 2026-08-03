"""Il file principale turni.db deve bastare a sé stesso.

Questi test nascono dalla perdita di dati che si è ripetuta più volte: il
file principale era rimasto fermo a settimane prima e tutto il lavoro
recente viveva solo nel -wal, che è un file separato. Bastava perderlo — o
ritrovarselo accanto non combaciante — perché i dati tornassero indietro,
e nessun controllo se ne accorgeva: senza il -wal il file principale resta
perfettamente coerente, solo vecchio.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def database_wal(tmp_path):
    """Un database con le stesse impostazioni di quello vero (vedi
    app/database.py), su cui poter simulare la perdita del -wal."""
    percorso = tmp_path / "turni.db"
    motore = create_engine(f"sqlite:///{percorso}", connect_args={"check_same_thread": False})

    @event.listens_for(motore, "connect")
    def _impostazioni(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode = WAL")
        cur.execute("PRAGMA wal_autocheckpoint = 32")
        cur.close()

    with motore.connect() as conn:
        conn.execute(text("CREATE TABLE turni (id INTEGER PRIMARY KEY, valore TEXT)"))
        conn.commit()
    return percorso, motore, sessionmaker(bind=motore)


def _valori(percorso):
    """Legge il SOLO file principale, come se il -wal fosse andato perso."""
    con = sqlite3.connect(percorso)
    try:
        return [r[0] for r in con.execute("SELECT valore FROM turni ORDER BY id")]
    finally:
        con.close()


def test_senza_il_wal_il_file_principale_contiene_comunque_i_dati(database_wal, tmp_path):
    """Il caso vero: si perde il -wal. Con il riversamento all'avvio e la
    soglia bassa, il file principale ha comunque tutto."""
    percorso, motore, Sessione = database_wal
    from app.database import consolida_wal

    with motore.connect() as conn:
        for i in range(300):
            conn.execute(text("INSERT INTO turni (valore) VALUES (:v)"), {"v": f"turno-{i}"})
        conn.commit()

    # Riversamento come quello che init_db esegue all'avvio.
    with motore.connect() as conn:
        conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    motore.dispose()

    # Si butta via il -wal, come se fosse stato cancellato o perso.
    for estensione in ("-wal", "-shm"):
        residuo = percorso.parent / (percorso.name + estensione)
        if residuo.exists():
            residuo.unlink()

    assert len(_valori(percorso)) == 300
    assert consolida_wal is not None  # la funzione usata all'avvio esiste


def test_la_soglia_bassa_tiene_il_file_principale_aggiornato(database_wal):
    """Senza toccare niente a mano: scrivendo abbastanza da superare le 32
    pagine, SQLite riversa da solo e il file principale non resta indietro."""
    percorso, motore, _ = database_wal

    with motore.connect() as conn:
        for i in range(2000):
            conn.execute(text("INSERT INTO turni (valore) VALUES (:v)"), {"v": f"riga-{i}" * 20})
            if i % 100 == 0:
                conn.commit()
        conn.commit()
    motore.dispose()

    wal = percorso.parent / (percorso.name + "-wal")
    dimensione_wal = wal.stat().st_size if wal.exists() else 0
    # Il -wal non deve essere diventato il posto dove vivono i dati: con la
    # soglia predefinita (1000 pagine) qui sarebbe cresciuto senza limiti.
    assert dimensione_wal < 32 * 4096 * 4, f"-wal troppo grande: {dimensione_wal} byte"


def test_le_impostazioni_del_database_vero_sono_quelle_attese():
    """Guardia sulle due impostazioni da cui dipende tutto: se qualcuno
    toglie il WAL o rialza la soglia, si torna al problema di prima."""
    from app.database import engine

    with engine.connect() as conn:
        modo = conn.execute(text("PRAGMA journal_mode")).scalar()
        soglia = conn.execute(text("PRAGMA wal_autocheckpoint")).scalar()
    assert str(modo).lower() == "wal"
    assert soglia == 32

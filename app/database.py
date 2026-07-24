from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _abilita_foreign_keys(dbapi_connection, connection_record):
    # WAL: più utenti dalla rete possono leggere mentre qualcuno scrive,
    # invece di bloccarsi a vicenda come nel modo di default di SQLite.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migra_schema():
    """create_all crea solo le tabelle che non esistono ancora: non
    aggiunge colonne a una tabella già presente con dati (qui: sedi, che
    esisteva prima di ordine_visualizzazione). Senza un vero sistema di
    migrazioni, il modo più semplice è un ALTER TABLE fatto a mano, reso
    sicuro da rilanciare a ogni avvio controllando prima se la colonna
    c'è già."""
    with engine.connect() as conn:
        colonne_sedi = {r[1] for r in conn.execute(text("PRAGMA table_info(sedi)"))}
        if "ordine_visualizzazione" not in colonne_sedi:
            conn.execute(text("ALTER TABLE sedi ADD COLUMN ordine_visualizzazione INTEGER NOT NULL DEFAULT 0"))
            conn.commit()

        colonne_dipendenti = {r[1] for r in conn.execute(text("PRAGMA table_info(dipendenti)"))}
        if "sottosezione" not in colonne_dipendenti:
            conn.execute(text("ALTER TABLE dipendenti ADD COLUMN sottosezione TEXT"))
            conn.commit()

        colonne_sedi = {r[1] for r in conn.execute(text("PRAGMA table_info(sedi)"))}
        if "copertura_minima_mattina" not in colonne_sedi:
            conn.execute(text("ALTER TABLE sedi ADD COLUMN copertura_minima_mattina INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE sedi ADD COLUMN copertura_minima_pomeriggio INTEGER NOT NULL DEFAULT 0"))
            # Riporta il vecchio minimo unico (valido per l'intera giornata)
            # su entrambe le fasce nuove, così un minimo già configurato non
            # sparisce silenziosamente al primo avvio dopo l'aggiornamento:
            # resta comunque da rivedere/correggere a mano in Sedi, visto che
            # non è detto che lo stesso numero fosse pensato per entrambe le
            # fasce separatamente.
            conn.execute(text(
                "UPDATE sedi SET copertura_minima_mattina = copertura_minima_ordinaria, "
                "copertura_minima_pomeriggio = copertura_minima_ordinaria"
            ))
            conn.commit()

        colonne_tipi_turno = {r[1] for r in conn.execute(text("PRAGMA table_info(tipi_turno)"))}
        if "fascia" not in colonne_tipi_turno:
            conn.execute(text("ALTER TABLE tipi_turno ADD COLUMN fascia TEXT"))
            conn.commit()


def init_db():
    from app import models  # noqa: F401  (registra i modelli su Base)

    Base.metadata.create_all(bind=engine)
    _migra_schema()

import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DB_PATH

logger = logging.getLogger("calendario_turni.database")

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
    # Quanto può crescere il -wal prima che SQLite lo riversi da solo dentro
    # turni.db. Il valore predefinito è 1000 pagine, cioè circa 4 MB: su un
    # archivio come questo, che di pagine ne ha meno di cento, vuol dire
    # MAI. È esattamente com'è andata: il file principale è rimasto fermo a
    # settimane prima e tutto il lavoro recente viveva solo nel -wal, che è
    # un file separato. Bastava perderlo, o ritrovarselo accanto non
    # combaciante, perché i dati "tornassero indietro" o si rompessero.
    #
    # Con 32 pagine (~128 KB) il riversamento avviene di continuo: turni.db
    # resta praticamente sempre aggiornato e il -wal non è mai portante.
    cursor.execute("PRAGMA wal_autocheckpoint = 32")
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

        if "email" not in colonne_dipendenti:
            conn.execute(text("ALTER TABLE dipendenti ADD COLUMN email TEXT"))
            conn.commit()

        # Memoria del turno che un'assenza ha sovrascritto, per poterlo
        # restituire se l'assenza viene rifiutata o cancellata (vedi
        # app/routers/assenze.py::_copri_giorni_con_assenza). Nullable
        # senza default: sulle righe già esistenti "nessuna memoria" è
        # esattamente lo stato giusto, e il ripristino si limita a non
        # scattare per le assenze approvate prima di questo aggiornamento.
        colonne_assegnazioni = {r[1] for r in conn.execute(text("PRAGMA table_info(assegnazioni_giornaliere)"))}
        if "tipo_turno_precedente_id" not in colonne_assegnazioni:
            conn.execute(text("ALTER TABLE assegnazioni_giornaliere ADD COLUMN tipo_turno_precedente_id INTEGER REFERENCES tipi_turno(id)"))
            conn.execute(text("ALTER TABLE assegnazioni_giornaliere ADD COLUMN origine_precedente TEXT"))
            conn.commit()

        # Assenza parziale (esce prima, entra dopo, qualche ora): stesso
        # pattern di Sostituzione.ora_inizio/ora_fine, vedi il modello.
        # Nullable senza default: sulle assenze già esistenti "nessun
        # orario" è esattamente il significato giusto, cioè giorno intero.
        colonne_assenze = {r[1] for r in conn.execute(text("PRAGMA table_info(assenze)"))}
        if "ora_inizio" not in colonne_assenze:
            conn.execute(text("ALTER TABLE assenze ADD COLUMN ora_inizio TIME"))
            conn.execute(text("ALTER TABLE assenze ADD COLUMN ora_fine TIME"))
            conn.commit()


def verifica_integrita() -> str | None:
    """Restituisce il problema riscontrato, o None se il database è sano.

    Un database SQLite danneggiato non si annuncia: ogni pagina che serve
    risponde "database disk image is malformed" e l'utente vede solo
    "Internal Server Error" su qualunque schermata, senza un motivo né un
    punto da cui partire. È già successo, ed è costato ore per capire di
    cosa si trattasse: meglio dirlo a chiare lettere nel log all'avvio,
    quando c'è ancora un backup recente da cui ripartire (vedi
    app/backup.py e la cartella backup accanto al database)."""
    try:
        with engine.connect() as conn:
            esito = conn.execute(text("PRAGMA integrity_check")).scalar()
    except Exception as e:  # il database non si apre nemmeno
        return str(e)
    return None if esito == "ok" else esito


def consolida_wal() -> bool:
    """Riversa dentro turni.db tutto ciò che sta ancora nel -wal, così il
    file principale è completo da solo. True se è riuscito del tutto.

    Va chiamato SOLO all'avvio, prima che partano i thread di sfondo e
    prima di servire richieste: è l'unico momento in cui nessun altro sta
    scrivendo. Farlo alla chiusura, come si era provato, significa scrivere
    sul database mentre il processo sta per uscire e i thread daemon
    vengono interrotti dove capita — ed è finita male.

    Perché serve: il -wal è un file separato da turni.db. Se il file
    principale resta indietro, tutto il lavoro recente vive solo lì dentro,
    e basta perderlo (o ritrovarselo accanto non combaciante) perché i dati
    tornino indietro di settimane senza che nessun controllo se ne accorga,
    visto che il file principale resta perfettamente coerente. Qui si toglie
    al -wal quel ruolo portante."""
    try:
        with engine.connect() as conn:
            # (bloccate, pagine_nel_wal, pagine_riversate): la prima è 0 se
            # il riversamento è riuscito senza trovare altri in mezzo.
            bloccate, _, _ = conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)")).fetchone()
        return bloccate == 0
    except Exception:
        logger.exception("Riversamento del -wal in %s non riuscito", DB_PATH)
        return False


def init_db():
    from app import models  # noqa: F401  (registra i modelli su Base)

    Base.metadata.create_all(bind=engine)
    _migra_schema()

    if not consolida_wal():
        logger.warning(
            "Il -wal accanto a %s non è stato riversato del tutto: qualcun altro sta usando "
            "il database in questo momento (un secondo server acceso?). Non è un danno, ma "
            "conviene accertarsi che ci sia un solo server in esecuzione.",
            DB_PATH,
        )

    problema = verifica_integrita()
    if problema is not None:
        logger.error(
            "DATABASE DANNEGGIATO (%s): %s. Il programma partirà comunque, ma le pagine "
            "che leggono i dati rovinati daranno errore. Ripristina l'ultimo backup buono "
            "dalla cartella backup accanto al database.",
            DB_PATH,
            problema,
        )

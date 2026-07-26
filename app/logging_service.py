import logging
from logging.handlers import RotatingFileHandler

from sqlalchemy.orm import Session

from app.models import LogModifica
from app.paths import cartella_dati

# Un file da 2 MB per cinque ricambi: abbastanza da coprire settimane di
# esercizio, poco abbastanza da restare apribile con il Blocco note su un PC
# d'ufficio.
_DIMENSIONE_MASSIMA_LOG = 2 * 1024 * 1024
_COPIE_LOG = 5

_configurato = False


def configura_logging() -> None:
    """Manda i log dell'applicazione su un file con data, nome del
    sottosistema e rotazione.

    Senza questa configurazione Python usa il gestore di ultima istanza:
    scrive su stderr, solo da WARNING in su, SENZA orario e SENZA dire quale
    parte del programma ha prodotto il messaggio. Nell'eseguibile
    impacchettato stderr finisce in log.txt (vedi server_app.py), un file in
    append che non veniva mai ruotato e cresceva senza limite.

    Il risultato pratico: alla segnalazione "il riepilogo di ieri sera non è
    partito", in log.txt c'era sì un traceback, ma senza sapere di quando
    fosse né da cosa arrivasse, in mezzo a settimane di righe di uvicorn.
    Diagnosi impossibile, per giunta da parte di chi non è tecnico.

    Idempotente: chiamarla due volte non raddoppia i messaggi.
    """
    global _configurato
    if _configurato:
        return
    _configurato = True

    logger_app = logging.getLogger("calendario_turni")
    logger_app.setLevel(logging.INFO)

    try:
        handler = RotatingFileHandler(
            cartella_dati() / "calendario_turni.log",
            maxBytes=_DIMENSIONE_MASSIMA_LOG,
            backupCount=_COPIE_LOG,
            encoding="utf-8",
        )
    except OSError:
        # Cartella non scrivibile: meglio restare senza file di log che
        # impedire l'avvio del programma per un problema di diagnostica.
        return

    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    logger_app.addHandler(handler)


def registra_modifica(
    db: Session,
    utente_id: int | None,
    tabella: str,
    record_id: int,
    azione: str,
    dettaglio: str | None = None,
) -> None:
    """Aggiunge una riga di log alla sessione corrente, senza fare commit:
    il chiamante fa commit insieme alla modifica che sta registrando, così
    la modifica e il suo log sono atomici."""
    db.add(
        LogModifica(
            utente_id=utente_id,
            tabella=tabella,
            record_id=record_id,
            azione=azione,
            dettaglio=dettaglio,
        )
    )

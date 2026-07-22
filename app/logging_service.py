from sqlalchemy.orm import Session

from app.models import LogModifica


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

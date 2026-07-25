"""Destinatari dell'allarme di copertura effettivi: legge prima la tabella
impostazioni_allarme_copertura (modificabile SOLO dall'amministratore in
/allarme-copertura), e solo se quella riga manca o è completamente vuota
ricade sulla lista statica ALLARME_COPERTURA_DESTINATARI di
app/email_config.py. Stesso schema già usato per l'IMAP in
app/impostazioni_email.py."""

from datetime import datetime

from sqlalchemy.orm import Session

from app import email_config
from app.models import ImpostazioneAllarmeCopertura


def _riga(db: Session) -> ImpostazioneAllarmeCopertura | None:
    return db.get(ImpostazioneAllarmeCopertura, 1)


def destinatari_effettivi(db: Session) -> list[str]:
    riga = _riga(db)
    if riga:
        indirizzi = [e.strip() for e in (riga.email_1, riga.email_2, riga.email_3) if e and e.strip()]
        if indirizzi:
            return indirizzi
    return email_config.ALLARME_COPERTURA_DESTINATARI


def campi_grezzi(db: Session) -> tuple[str, str, str]:
    """I tre campi così come salvati (non la lista effettiva sopra, che
    include il ripiego sul file): servono a precompilare il form di
    modifica con quello che è stato davvero salvato da interfaccia, non con
    valori presi dal file che sembrerebbero già salvati se mostrati lì."""
    riga = _riga(db)
    if riga is None:
        return "", "", ""
    return riga.email_1 or "", riga.email_2 or "", riga.email_3 or ""


def allarme_copertura_configurato(db: Session) -> bool:
    """True solo se SMTP (sempre statico, da file) e almeno un destinatario
    (da interfaccia o da file) sono compilati."""
    return bool(
        email_config.SMTP_HOST
        and email_config.SMTP_UTENTE
        and email_config.SMTP_PASSWORD
        and destinatari_effettivi(db)
    )


def salva_destinatari(db: Session, utente_id: int, email_1: str, email_2: str, email_3: str) -> None:
    riga = _riga(db)
    if riga is None:
        riga = ImpostazioneAllarmeCopertura(id=1)
        db.add(riga)
    riga.email_1 = email_1.strip() or None
    riga.email_2 = email_2.strip() or None
    riga.email_3 = email_3.strip() or None
    riga.aggiornato_il = datetime.now()
    riga.aggiornato_da = utente_id
    db.commit()

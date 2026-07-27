"""Destinatari del riepilogo giornaliero effettivi: legge prima la tabella
impostazioni_riepilogo_giornaliero (modificabile SOLO dall'amministratore in
/riepilogo-giornaliero), e solo se quella riga manca o è completamente
vuota ricade sulla lista statica RIEPILOGO_GIORNALIERO_DESTINATARI di
app/email_config.py. Stesso schema di app/impostazioni_allarme_copertura.py
(a sua volta copiato da app/impostazioni_email.py)."""

from datetime import datetime

from sqlalchemy.orm import Session

from app import email_config
from app.models import ImpostazioneRiepilogoGiornaliero


def _riga(db: Session) -> ImpostazioneRiepilogoGiornaliero | None:
    return db.get(ImpostazioneRiepilogoGiornaliero, 1)


def destinatari_effettivi(db: Session) -> list[str]:
    riga = _riga(db)
    if riga:
        indirizzi = [e.strip() for e in (riga.email_1, riga.email_2, riga.email_3) if e and e.strip()]
        if indirizzi:
            return indirizzi
    return email_config.RIEPILOGO_GIORNALIERO_DESTINATARI


def campi_grezzi(db: Session) -> tuple[str, str, str]:
    """I tre campi così come salvati (non la lista effettiva sopra, che
    include il ripiego sul file): servono a precompilare il form di
    modifica con quello che è stato davvero salvato da interfaccia, non con
    valori presi dal file che sembrerebbero già salvati se mostrati lì."""
    riga = _riga(db)
    if riga is None:
        return "", "", ""
    return riga.email_1 or "", riga.email_2 or "", riga.email_3 or ""


def riepilogo_giornaliero_configurato(db: Session) -> bool:
    """True solo se SMTP (sempre statico, da file) e almeno un destinatario
    (da interfaccia o da file) sono compilati."""
    return bool(
        email_config.SMTP_HOST
        and email_config.SMTP_UTENTE
        and email_config.SMTP_PASSWORD
        and destinatari_effettivi(db)
    )


def salva_destinatari(db: Session, utente_id: int, email_1: str, email_2: str, email_3: str) -> None:
    """NON fa commit: lo fa il chiamante, come per registra_modifica (vedi
    app/logging_service.py). Committare qui dentro lascerebbe la riga di
    log aggiunta subito dopo dal router in una transazione mai chiusa —
    esattamente l'errore già corretto per le impostazioni IMAP e per queste
    stesse dell'allarme di copertura (vedi
    app/impostazioni_allarme_copertura.py)."""
    riga = _riga(db)
    if riga is None:
        riga = ImpostazioneRiepilogoGiornaliero(id=1)
        db.add(riga)
    riga.email_1 = email_1.strip() or None
    riga.email_2 = email_2.strip() or None
    riga.email_3 = email_3.strip() or None
    riga.aggiornato_il = datetime.now()
    riga.aggiornato_da = utente_id

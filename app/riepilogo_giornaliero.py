"""Riepilogo giornaliero automatico di chi è nei vari presidi il giorno
dopo, inviato via email al referente della Camera dei Deputati entro
l'orario configurato (email_config.RIEPILOGO_GIORNALIERO_ORA). Sostituisce
l'invio manuale che oggi fa ogni giorno una delle persone che segnano turni
e sostituzioni."""

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import email_config, impostazioni_riepilogo_giornaliero
from app.database import SessionLocal
from app.email_service import _invia_ora
from app.models import InvioGiornaliero
from app.routers.copertura import calcola_copertura
from app.templates import templates

logger = logging.getLogger("calendario_turni.riepilogo_giornaliero")


def _ora_configurata_o_none(testo: str) -> time | None:
    try:
        return time.fromisoformat(testo)
    except ValueError:
        return None


def genera_html_riepilogo(db: Session, data_riepilogo: date) -> str:
    blocchi = calcola_copertura(db, data_riepilogo)
    return templates.env.get_template("email_riepilogo_giornaliero.html").render(
        data_riepilogo=data_riepilogo, blocchi=blocchi
    )


def invia_riepilogo_giornaliero(db: Session, forza: bool = False, inviato_da: int | None = None) -> bool:
    """Invia il riepilogo di DOMANI ai destinatari configurati, usando la
    sessione passata dal chiamante (mai una aperta qui: una route usa la sua
    Depends(get_db), rispettando l'override dei test; il thread di sfondo ne
    apre una sua, vedi controlla_e_invia_se_dovuto). Senza forza=True, non
    rimanda nulla se è già stato inviato oggi per la stessa data (evita
    doppi invii, es. per un riavvio del server proprio a cavallo dell'orario
    configurato). Restituisce True solo se ha inviato davvero."""
    if not impostazioni_riepilogo_giornaliero.riepilogo_giornaliero_configurato(db):
        return False

    domani = date.today() + timedelta(days=1)
    gia_inviato = db.query(InvioGiornaliero).filter_by(data_riepilogo=domani).first()
    if gia_inviato is not None and not forza:
        return False

    destinatari = impostazioni_riepilogo_giornaliero.destinatari_effettivi(db)
    corpo_html = genera_html_riepilogo(db, domani)
    oggetto = f"Presidi CD Servizi — {domani.strftime('%d/%m/%Y')}"
    riuscito = _invia_ora(oggetto, corpo_html, destinatari=destinatari)
    if not riuscito:
        return False

    try:
        if gia_inviato is not None:
            # Reinvio manuale forzato di un giorno già coperto: aggiorna la
            # riga esistente invece di violare l'unicità su data_riepilogo.
            gia_inviato.inviato_il = datetime.now()
            gia_inviato.destinatari = ", ".join(destinatari)
            gia_inviato.manuale = True
            gia_inviato.inviato_da = inviato_da
        else:
            db.add(InvioGiornaliero(
                data_riepilogo=domani,
                destinatari=", ".join(destinatari),
                manuale=inviato_da is not None,
                inviato_da=inviato_da,
            ))
        db.commit()
    except IntegrityError:
        # Il controllo "già inviato?" più sopra e questo insert/update non
        # sono atomici: se un'altra chiamata concorrente (due richieste quasi
        # simultanee, o il thread di sfondo e un "Invia ora" manuale) ha
        # registrato la stessa data_riepilogo nel frattempo, questo commit
        # sbatte contro l'UniqueConstraint. La mail è comunque già stata
        # spedita da questa chiamata: non c'è modo di "de-inviarla", ma non
        # dobbiamo almeno far esplodere un 500 né lasciare la sessione in uno
        # stato inconsistente.
        db.rollback()
        logger.warning(
            "Riepilogo giornaliero per %s già registrato da un invio concorrente: mail spedita due volte.",
            domani,
        )
    return True


def controlla_e_invia_se_dovuto() -> bool:
    """Da chiamare periodicamente da un thread di sfondo (vedi main.py): non
    fa nulla se l'invio automatico non è abilitato, se non è ancora l'ora
    configurata, o se è già partito oggi. Non solleva mai eccezioni. Qui (e
    solo qui) si apre una sessione diretta, perché non c'è nessuna richiesta
    HTTP da cui riceverne una già pronta."""
    try:
        if not email_config.RIEPILOGO_GIORNALIERO_ABILITATO:
            return False
        ora_configurata = _ora_configurata_o_none(email_config.RIEPILOGO_GIORNALIERO_ORA)
        if ora_configurata is None:
            logger.error("RIEPILOGO_GIORNALIERO_ORA non valido: %r", email_config.RIEPILOGO_GIORNALIERO_ORA)
            return False
        if datetime.now().time() < ora_configurata:
            return False
        db = SessionLocal()
        try:
            return invia_riepilogo_giornaliero(db, forza=False)
        finally:
            db.close()
    except Exception:
        logger.exception("Controllo/invio del riepilogo giornaliero fallito")
        return False

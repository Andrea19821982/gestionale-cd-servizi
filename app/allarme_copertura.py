"""Preavviso interno ai gestori (non al referente Camera dei Deputati, vedi
invece app/riepilogo_giornaliero.py) se domani un palazzo (o un comparto a
copertura propria) risulterà sotto la copertura minima configurata, per
mattina o pomeriggio (vedi Sede.copertura_minima_mattina/pomeriggio,
SottosezioneCopertura e Sala.copertura_minima_aggiuntiva): dà ancora tempo
per organizzare una sostituzione prima del cutoff delle 20:00 del riepilogo
giornaliero."""

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import email_config
from app.database import SessionLocal
from app.email_service import _invia_ora
from app.models import AllarmeCoperturaInviato
from app.routers.copertura import calcola_copertura
from app.templates import templates

logger = logging.getLogger("calendario_turni.allarme_copertura")


def _ora_configurata_o_none(testo: str) -> time | None:
    try:
        return time.fromisoformat(testo)
    except ValueError:
        return None


def blocchi_carenti(db: Session, data_obj: date) -> list[dict]:
    """Solo i blocchi di calcola_copertura che risultano sotto il minimo:
    usata sia dall'anteprima interattiva sia dall'email, stessa logica in
    entrambi i posti."""
    return [blocco for blocco in calcola_copertura(db, data_obj) if blocco["sotto_minimo"]]


def genera_html_allarme(blocchi: list[dict], data_riferimento: date) -> str:
    return templates.env.get_template("email_allarme_copertura.html").render(
        data_riferimento=data_riferimento, blocchi=blocchi
    )


def controlla_e_segnala_carenza(db: Session, forza: bool = False, inviato_da: int | None = None) -> bool:
    """Controlla la copertura di DOMANI e avvisa i gestori se qualche
    palazzo è sotto il minimo, usando la sessione passata dal chiamante (mai
    una aperta qui: vedi la stessa scelta in riepilogo_giornaliero.py). Senza
    forza=True, non rimanda nulla se è già stato segnalato oggi per lo stesso
    giorno. Non manda nulla se nessun palazzo è carente. Restituisce True
    solo se ha inviato davvero."""
    if not email_config.allarme_copertura_configurato():
        return False

    domani = date.today() + timedelta(days=1)
    carenti = blocchi_carenti(db, domani)
    if not carenti:
        return False

    gia_inviato = db.query(AllarmeCoperturaInviato).filter_by(data_riferimento=domani).first()
    if gia_inviato is not None and not forza:
        return False

    nomi_palazzi = ", ".join(blocco["sede"].nome for blocco in carenti)
    corpo_html = genera_html_allarme(carenti, domani)
    oggetto = f"Attenzione: copertura sotto il minimo per domani {domani.strftime('%d/%m/%Y')} — {nomi_palazzi}"
    riuscito = _invia_ora(oggetto, corpo_html, destinatari=email_config.ALLARME_COPERTURA_DESTINATARI)
    if not riuscito:
        return False

    try:
        if gia_inviato is not None:
            # Reinvio manuale forzato di un giorno già segnalato: aggiorna la
            # riga esistente invece di violare l'unicità su data_riferimento.
            gia_inviato.inviato_il = datetime.now()
            gia_inviato.destinatari = ", ".join(email_config.ALLARME_COPERTURA_DESTINATARI)
            gia_inviato.palazzi_carenti = nomi_palazzi
            gia_inviato.manuale = True
            gia_inviato.inviato_da = inviato_da
        else:
            db.add(AllarmeCoperturaInviato(
                data_riferimento=domani,
                destinatari=", ".join(email_config.ALLARME_COPERTURA_DESTINATARI),
                palazzi_carenti=nomi_palazzi,
                manuale=inviato_da is not None,
                inviato_da=inviato_da,
            ))
        db.commit()
    except IntegrityError:
        # Stessa race di app/riepilogo_giornaliero.py: il controllo "già
        # segnalato?" e questo insert/update non sono atomici. La mail è
        # comunque già stata spedita da questa chiamata: non propaghiamo un
        # 500 né lasciamo la sessione in uno stato inconsistente.
        db.rollback()
        logger.warning(
            "Allarme di copertura per %s già registrato da un invio concorrente: mail spedita due volte.",
            domani,
        )
    return True


def controlla_e_invia_se_dovuto() -> bool:
    """Da chiamare periodicamente da un thread di sfondo (vedi main.py): non
    fa nulla se il controllo automatico non è abilitato, se non è ancora
    l'ora configurata, se è già scattato oggi, o se nessun palazzo è carente.
    Non solleva mai eccezioni. Apre qui (e solo qui) una sessione diretta,
    perché non c'è nessuna richiesta HTTP da cui riceverne una già pronta."""
    try:
        if not email_config.ALLARME_COPERTURA_ABILITATO:
            return False
        ora_configurata = _ora_configurata_o_none(email_config.ALLARME_COPERTURA_ORA)
        if ora_configurata is None:
            logger.error("ALLARME_COPERTURA_ORA non valido: %r", email_config.ALLARME_COPERTURA_ORA)
            return False
        if datetime.now().time() < ora_configurata:
            return False
        db = SessionLocal()
        try:
            return controlla_e_segnala_carenza(db, forza=False)
        finally:
            db.close()
    except Exception:
        logger.exception("Controllo/invio dell'allarme di copertura fallito")
        return False

"""Pagina di controllo del riepilogo giornaliero automatico (vedi
app/riepilogo_giornaliero.py): mostra se è configurato, lo storico degli
invii e un pulsante per mandarlo subito (utile per un test o per un
reinvio dopo una modifica dell'ultimo minuto)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import email_config, impostazioni_riepilogo_giornaliero
from app.auth import RUOLI_SCRITTURA_ANAGRAFICA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import InvioGiornaliero, Utente
from app.riepilogo_giornaliero import invia_riepilogo_giornaliero
from app.routers.copertura import calcola_copertura
from app.templates import templates

router = APIRouter()


@router.get("/riepilogo-giornaliero")
def stato_riepilogo_giornaliero(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    domani = date.today() + timedelta(days=1)
    invii_recenti = (
        db.query(InvioGiornaliero)
        .order_by(InvioGiornaliero.data_riepilogo.desc())
        .limit(14)
        .all()
    )
    gia_inviato_domani = db.query(InvioGiornaliero).filter_by(data_riepilogo=domani).first() is not None
    blocchi_anteprima = calcola_copertura(db, domani)
    email_1, email_2, email_3 = impostazioni_riepilogo_giornaliero.campi_grezzi(db)

    return templates.TemplateResponse(
        request,
        "riepilogo_giornaliero.html",
        {
            "utente": utente,
            "domani": domani,
            "configurato": impostazioni_riepilogo_giornaliero.riepilogo_giornaliero_configurato(db),
            "abilitato": email_config.RIEPILOGO_GIORNALIERO_ABILITATO,
            "destinatari": impostazioni_riepilogo_giornaliero.destinatari_effettivi(db),
            "email_1": email_1,
            "email_2": email_2,
            "email_3": email_3,
            "ora_configurata": email_config.RIEPILOGO_GIORNALIERO_ORA,
            "gia_inviato_domani": gia_inviato_domani,
            "invii_recenti": invii_recenti,
            "blocchi_anteprima": blocchi_anteprima,
        },
    )


@router.post("/riepilogo-giornaliero/destinatari")
def imposta_destinatari_riepilogo_giornaliero(
    request: Request,
    email_1: str = Form(""),
    email_2: str = Form(""),
    email_3: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Solo amministratore (RUOLI_SCRITTURA_ANAGRAFICA = solo
    "amministratore"): stessa scelta già fatta per i destinatari
    dell'allarme di copertura, vedi app/routers/allarme_copertura.py."""
    impostazioni_riepilogo_giornaliero.salva_destinatari(db, utente.id, email_1, email_2, email_3)
    registra_modifica(
        db, utente.id, "impostazioni_riepilogo_giornaliero", 1, "modifica",
        f"email_1={email_1.strip()}, email_2={email_2.strip()}, email_3={email_3.strip()}",
    )
    db.commit()  # impostazione e riga di log insieme, o nessuna delle due
    imposta_flash(request, "Destinatari del riepilogo giornaliero aggiornati.", tipo="ok")
    return RedirectResponse("/riepilogo-giornaliero", status_code=303)


@router.post("/riepilogo-giornaliero/invia-ora")
def invia_ora_riepilogo_giornaliero(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    if not impostazioni_riepilogo_giornaliero.riepilogo_giornaliero_configurato(db):
        imposta_flash(
            request,
            "Il riepilogo giornaliero non è ancora configurato: manca SMTP (in "
            "app/email_config_locale.py) e/o i destinatari (qui sotto, o nello stesso file).",
            tipo="errore",
        )
        return RedirectResponse("/riepilogo-giornaliero", status_code=303)

    riuscito = invia_riepilogo_giornaliero(db, forza=True, inviato_da=utente.id)
    if riuscito:
        imposta_flash(request, "Riepilogo di domani inviato.", tipo="avviso")
    else:
        imposta_flash(request, "Invio fallito: controlla i log del server e i parametri SMTP.", tipo="errore")
    return RedirectResponse("/riepilogo-giornaliero", status_code=303)

"""Pagina di controllo del riepilogo giornaliero automatico (vedi
app/riepilogo_giornaliero.py): mostra se è configurato, lo storico degli
invii e un pulsante per mandarlo subito (utile per un test o per un
reinvio dopo una modifica dell'ultimo minuto)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import email_config
from app.auth import RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.flash import imposta_flash
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

    return templates.TemplateResponse(
        request,
        "riepilogo_giornaliero.html",
        {
            "utente": utente,
            "domani": domani,
            "configurato": email_config.riepilogo_giornaliero_configurato(),
            "abilitato": email_config.RIEPILOGO_GIORNALIERO_ABILITATO,
            "destinatari": email_config.RIEPILOGO_GIORNALIERO_DESTINATARI,
            "ora_configurata": email_config.RIEPILOGO_GIORNALIERO_ORA,
            "gia_inviato_domani": gia_inviato_domani,
            "invii_recenti": invii_recenti,
            "blocchi_anteprima": blocchi_anteprima,
        },
    )


@router.post("/riepilogo-giornaliero/invia-ora")
def invia_ora_riepilogo_giornaliero(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    if not email_config.riepilogo_giornaliero_configurato():
        imposta_flash(
            request,
            "Il riepilogo giornaliero non è ancora configurato: compila SMTP e i destinatari in "
            "app/email_config_locale.py prima di poterlo inviare.",
            tipo="errore",
        )
        return RedirectResponse("/riepilogo-giornaliero", status_code=303)

    riuscito = invia_riepilogo_giornaliero(db, forza=True, inviato_da=utente.id)
    if riuscito:
        imposta_flash(request, "Riepilogo di domani inviato.", tipo="avviso")
    else:
        imposta_flash(request, "Invio fallito: controlla i log del server e i parametri SMTP.", tipo="errore")
    return RedirectResponse("/riepilogo-giornaliero", status_code=303)

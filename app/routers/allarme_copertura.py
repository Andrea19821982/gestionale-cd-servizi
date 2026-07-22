"""Pagina di controllo del preavviso interno di carenza di copertura (vedi
app/allarme_copertura.py): mostra se è configurato, lo storico degli invii e
un pulsante per controllare/inviare subito."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import email_config
from app.allarme_copertura import blocchi_carenti, controlla_e_segnala_carenza
from app.auth import RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.flash import imposta_flash
from app.models import AllarmeCoperturaInviato, Utente
from app.templates import templates

router = APIRouter()


@router.get("/allarme-copertura")
def stato_allarme_copertura(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    domani = date.today() + timedelta(days=1)
    invii_recenti = (
        db.query(AllarmeCoperturaInviato)
        .order_by(AllarmeCoperturaInviato.data_riferimento.desc())
        .limit(14)
        .all()
    )
    gia_inviato_domani = db.query(AllarmeCoperturaInviato).filter_by(data_riferimento=domani).first() is not None
    blocchi_anteprima = blocchi_carenti(db, domani)

    return templates.TemplateResponse(
        request,
        "allarme_copertura.html",
        {
            "utente": utente,
            "domani": domani,
            "configurato": email_config.allarme_copertura_configurato(),
            "abilitato": email_config.ALLARME_COPERTURA_ABILITATO,
            "destinatari": email_config.ALLARME_COPERTURA_DESTINATARI,
            "ora_configurata": email_config.ALLARME_COPERTURA_ORA,
            "gia_inviato_domani": gia_inviato_domani,
            "invii_recenti": invii_recenti,
            "blocchi_anteprima": blocchi_anteprima,
        },
    )


@router.post("/allarme-copertura/invia-ora")
def invia_ora_allarme_copertura(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    if not email_config.allarme_copertura_configurato():
        imposta_flash(
            request,
            "L'allarme di copertura non è ancora configurato: compila SMTP e i destinatari in "
            "app/email_config_locale.py prima di poterlo inviare.",
            tipo="errore",
        )
        return RedirectResponse("/allarme-copertura", status_code=303)

    riuscito = controlla_e_segnala_carenza(db, forza=True, inviato_da=utente.id)
    if riuscito:
        imposta_flash(request, "Allarme di copertura inviato.", tipo="avviso")
    else:
        imposta_flash(
            request,
            "Nessun invio: o nessun palazzo è sotto il minimo per domani, o l'invio è fallito (controlla i log del server).",
            tipo="errore",
        )
    return RedirectResponse("/allarme-copertura", status_code=303)

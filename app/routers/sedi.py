from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_ANAGRAFICA, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.logging_service import registra_modifica
from app.models import Sede, Utente
from app.templates import templates
from app.utils import checkbox_a_bool, ottieni_o_404

router = APIRouter()


def _intero_non_negativo_o_400(valore: str) -> int:
    try:
        numero = int(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Valore non valido: {valore!r}")
    if numero < 0:
        raise HTTPException(status_code=400, detail="Il valore non può essere negativo.")
    return numero


@router.get("/sedi")
def elenco_sedi(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    sedi = db.query(Sede).order_by(Sede.nome).all()
    return templates.TemplateResponse(
        request, "sedi.html", {"sedi": sedi, "utente": utente}
    )


@router.post("/sedi/nuova")
def crea_sede(
    request: Request,
    nome: str = Form(...),
    colore_hex: str = Form(...),
    copertura_minima_ordinaria: str = Form("0"),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    sede = Sede(
        nome=nome.strip(),
        colore_hex=colore_hex.strip(),
        attivo=True,
        copertura_minima_ordinaria=_intero_non_negativo_o_400(copertura_minima_ordinaria),
    )
    db.add(sede)
    db.flush()
    registra_modifica(db, utente.id, "sedi", sede.id, "creazione", f"nome={sede.nome}")
    db.commit()
    return RedirectResponse("/sedi", status_code=303)


@router.post("/sedi/{sede_id}/modifica")
def modifica_sede(
    request: Request,
    sede_id: int,
    nome: str = Form(...),
    colore_hex: str = Form(...),
    copertura_minima_ordinaria: str = Form("0"),
    attivo: str = Form(None),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    sede = ottieni_o_404(db, Sede, sede_id)
    sede.nome = nome.strip()
    sede.colore_hex = colore_hex.strip()
    sede.copertura_minima_ordinaria = _intero_non_negativo_o_400(copertura_minima_ordinaria)
    sede.attivo = checkbox_a_bool(attivo)
    registra_modifica(
        db, utente.id, "sedi", sede.id, "modifica",
        f"nome={sede.nome}, colore_hex={sede.colore_hex}, copertura_minima_ordinaria={sede.copertura_minima_ordinaria}, attivo={sede.attivo}",
    )
    db.commit()
    return RedirectResponse("/sedi", status_code=303)

from datetime import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_ANAGRAFICA, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.logging_service import registra_modifica
from app.models import TipoTurno, Utente
from app.templates import templates
from app.utils import ottieni_o_404

router = APIRouter()


def _ora_o_400(valore: str) -> time:
    try:
        return time.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Orario non valido: {valore!r}")


@router.get("/tipi-turno")
def elenco_tipi_turno(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    tipi = db.query(TipoTurno).order_by(TipoTurno.ora_inizio).all()
    return templates.TemplateResponse(
        request, "tipi_turno.html", {"tipi": tipi, "utente": utente}
    )


@router.post("/tipi-turno/nuovo")
def crea_tipo_turno(
    request: Request,
    etichetta: str = Form(...),
    ora_inizio: str = Form(...),
    ora_fine: str = Form(...),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    tipo = TipoTurno(
        etichetta=etichetta.strip(),
        ora_inizio=_ora_o_400(ora_inizio),
        ora_fine=_ora_o_400(ora_fine),
    )
    db.add(tipo)
    db.flush()
    registra_modifica(
        db, utente.id, "tipi_turno", tipo.id, "creazione",
        f"etichetta={tipo.etichetta}, {ora_inizio}-{ora_fine}",
    )
    db.commit()
    return RedirectResponse("/tipi-turno", status_code=303)


@router.post("/tipi-turno/{tipo_id}/modifica")
def modifica_tipo_turno(
    request: Request,
    tipo_id: int,
    etichetta: str = Form(...),
    ora_inizio: str = Form(...),
    ora_fine: str = Form(...),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    tipo = ottieni_o_404(db, TipoTurno, tipo_id)
    tipo.etichetta = etichetta.strip()
    tipo.ora_inizio = _ora_o_400(ora_inizio)
    tipo.ora_fine = _ora_o_400(ora_fine)
    registra_modifica(
        db, utente.id, "tipi_turno", tipo.id, "modifica",
        f"etichetta={tipo.etichetta}, {ora_inizio}-{ora_fine}",
    )
    db.commit()
    return RedirectResponse("/tipi-turno", status_code=303)

from datetime import date, time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.email_service import invia_notifica_asincrona
from app.logging_service import registra_modifica
from app.models import Dipendente, Sede, Sostituzione, Utente
from app.templates import templates
from app.utils import ottieni_o_404

router = APIRouter()


def _data_o_400(valore: str) -> date:
    try:
        return date.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data non valida: {valore!r}")


def _ora_opzionale_o_400(valore: str) -> time | None:
    if not valore:
        return None
    try:
        return time.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Orario non valido: {valore!r}")


def _esiste_gia_sostituzione_giorno_intero(db: Session, dipendente_partente_id: int, data_sost: date) -> bool:
    return (
        db.query(Sostituzione)
        .filter(
            Sostituzione.dipendente_partente_id == dipendente_partente_id,
            Sostituzione.data == data_sost,
            Sostituzione.ora_inizio.is_(None),
        )
        .first()
        is not None
    )


@router.get("/sostituzioni")
def elenco_sostituzioni(
    request: Request,
    dipendente_id: int | None = None,
    data_da: str | None = None,
    data_a: str | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    query = db.query(Sostituzione)
    if dipendente_id:
        query = query.filter(
            (Sostituzione.dipendente_partente_id == dipendente_id)
            | (Sostituzione.dipendente_sostituto_id == dipendente_id)
        )
    if data_da:
        query = query.filter(Sostituzione.data >= _data_o_400(data_da))
    if data_a:
        query = query.filter(Sostituzione.data <= _data_o_400(data_a))
    sostituzioni = query.order_by(Sostituzione.data.desc()).all()

    dipendenti = db.query(Dipendente).order_by(Dipendente.cognome, Dipendente.nome).all()
    sedi = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712

    return templates.TemplateResponse(
        request,
        "sostituzioni.html",
        {
            "sostituzioni": sostituzioni,
            "dipendenti": dipendenti,
            "sedi": sedi,
            "utente": utente,
            "filtri": {
                "dipendente_id": dipendente_id,
                "data_da": data_da or "",
                "data_a": data_a or "",
            },
        },
    )


@router.post("/sostituzioni/nuova")
def crea_sostituzione(
    dipendente_partente_id: int = Form(...),
    sede_partenza_id: int = Form(...),
    dipendente_sostituto_id: int = Form(...),
    sede_arrivo_id: int = Form(...),
    data: str = Form(...),
    ora_inizio: str = Form(""),
    ora_fine: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    if dipendente_partente_id == dipendente_sostituto_id:
        raise HTTPException(status_code=400, detail="Il dipendente non può sostituire se stesso.")

    dipendente_partente = ottieni_o_404(db, Dipendente, dipendente_partente_id)
    dipendente_sostituto = ottieni_o_404(db, Dipendente, dipendente_sostituto_id)
    sede_partenza = ottieni_o_404(db, Sede, sede_partenza_id)
    sede_arrivo = ottieni_o_404(db, Sede, sede_arrivo_id)

    data_sost = _data_o_400(data)
    inizio = _ora_opzionale_o_400(ora_inizio)
    fine = _ora_opzionale_o_400(ora_fine)
    if (inizio is None) != (fine is None):
        raise HTTPException(
            status_code=400,
            detail="Indica sia l'ora di inizio sia l'ora di fine, oppure lasciale entrambe vuote per l'intera giornata.",
        )
    if inizio is not None and fine <= inizio:
        raise HTTPException(status_code=400, detail="L'ora fine deve essere successiva all'ora inizio.")

    if inizio is None and _esiste_gia_sostituzione_giorno_intero(db, dipendente_partente_id, data_sost):
        raise HTTPException(
            status_code=400,
            detail="Esiste già una sostituzione per l'intera giornata per questo dipendente in questa data.",
        )

    sostituzione = Sostituzione(
        data=data_sost,
        dipendente_partente_id=dipendente_partente_id,
        sede_partenza_id=sede_partenza_id,
        dipendente_sostituto_id=dipendente_sostituto_id,
        sede_arrivo_id=sede_arrivo_id,
        ora_inizio=inizio,
        ora_fine=fine,
        note=note.strip() or None,
        creato_da=utente.id,
    )
    db.add(sostituzione)
    db.flush()
    registra_modifica(
        db, utente.id, "sostituzioni", sostituzione.id, "creazione",
        f"dipendente_partente_id={dipendente_partente_id}, dipendente_sostituto_id={dipendente_sostituto_id}, "
        f"data={data_sost.isoformat()}, ora_inizio={ora_inizio or 'intera giornata'}, ora_fine={ora_fine or ''}",
    )
    db.commit()

    orario = f"{ora_inizio}-{ora_fine}" if inizio is not None else "intera giornata"
    invia_notifica_asincrona(
        f"Sostituzione registrata: {dipendente_partente.cognome} {dipendente_partente.nome}",
        "email_sostituzione.html",
        {
            "data": data_sost.isoformat(),
            "dipendente_partente_nome": f"{dipendente_partente.cognome} {dipendente_partente.nome}",
            "sede_partenza_nome": sede_partenza.nome,
            "dipendente_sostituto_nome": f"{dipendente_sostituto.cognome} {dipendente_sostituto.nome}",
            "sede_arrivo_nome": sede_arrivo.nome,
            "orario": orario,
            "note": sostituzione.note,
            "registrato_da": utente.username,
        },
    )
    return RedirectResponse("/sostituzioni", status_code=303)


@router.post("/sostituzioni/{sostituzione_id}/elimina")
def elimina_sostituzione(
    sostituzione_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    sostituzione = ottieni_o_404(db, Sostituzione, sostituzione_id)
    dettaglio = (
        f"dipendente_partente_id={sostituzione.dipendente_partente_id}, "
        f"dipendente_sostituto_id={sostituzione.dipendente_sostituto_id}, data={sostituzione.data.isoformat()}"
    )
    db.delete(sostituzione)
    registra_modifica(db, utente.id, "sostituzioni", sostituzione_id, "cancellazione", dettaglio)
    db.commit()
    return RedirectResponse("/sostituzioni", status_code=303)

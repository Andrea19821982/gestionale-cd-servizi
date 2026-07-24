from datetime import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_ANAGRAFICA, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import FASCE_TURNO_VALIDE, AssegnazioneGiornaliera, PatternTurno, TipoTurno, Utente
from app.templates import templates
from app.utils import ottieni_o_404

router = APIRouter()


def _ora_o_400(valore: str) -> time:
    try:
        return time.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Orario non valido: {valore!r}")


def _fascia_o_400(valore: str) -> str | None:
    """Stringa vuota -> non ancora classificato (None): quel turno non
    concorre al minimo di copertura di nessuna fascia finché non viene
    classificato qui (vedi calcola_copertura in app/routers/copertura.py)."""
    valore = valore.strip()
    if not valore:
        return None
    if valore not in FASCE_TURNO_VALIDE:
        raise HTTPException(status_code=400, detail=f"Fascia non valida: {valore!r}")
    return valore


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
    fascia: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    tipo = TipoTurno(
        etichetta=etichetta.strip(),
        ora_inizio=_ora_o_400(ora_inizio),
        ora_fine=_ora_o_400(ora_fine),
        fascia=_fascia_o_400(fascia),
    )
    db.add(tipo)
    db.flush()
    registra_modifica(
        db, utente.id, "tipi_turno", tipo.id, "creazione",
        f"etichetta={tipo.etichetta}, {ora_inizio}-{ora_fine}, fascia={tipo.fascia}",
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
    fascia: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    tipo = ottieni_o_404(db, TipoTurno, tipo_id)
    tipo.etichetta = etichetta.strip()
    tipo.ora_inizio = _ora_o_400(ora_inizio)
    tipo.ora_fine = _ora_o_400(ora_fine)
    tipo.fascia = _fascia_o_400(fascia)
    registra_modifica(
        db, utente.id, "tipi_turno", tipo.id, "modifica",
        f"etichetta={tipo.etichetta}, {ora_inizio}-{ora_fine}, fascia={tipo.fascia}",
    )
    db.commit()
    return RedirectResponse("/tipi-turno", status_code=303)


@router.post("/tipi-turno/{tipo_id}/elimina")
def elimina_tipo_turno(
    request: Request,
    tipo_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Un tipo turno usato in qualche turno assegnato o nel pattern base di
    un dipendente non si può eliminare: bisogna prima riassegnarlo a un
    altro tipo, altrimenti quei turni/quel pattern resterebbero orfani."""
    tipo = ottieni_o_404(db, TipoTurno, tipo_id)
    n_assegnazioni = (
        db.query(AssegnazioneGiornaliera).filter(AssegnazioneGiornaliera.tipo_turno_id == tipo_id).count()
    )
    n_pattern = (
        db.query(PatternTurno)
        .filter(
            (PatternTurno.turno_settimana_dispari_id == tipo_id)
            | (PatternTurno.turno_settimana_pari_id == tipo_id)
        )
        .count()
    )
    if n_assegnazioni > 0 or n_pattern > 0:
        dettaglio_uso = f"{n_assegnazioni} turni assegnati"
        if n_pattern:
            dettaglio_uso += f" e nel pattern base di {n_pattern} dipendenti"
        imposta_flash(
            request,
            f'Non posso eliminare "{tipo.etichetta}": è usato in {dettaglio_uso}. '
            "Riassegna prima quei turni a un altro tipo.",
            tipo="errore",
        )
        return RedirectResponse("/tipi-turno", status_code=303)

    etichetta = tipo.etichetta
    db.delete(tipo)
    registra_modifica(db, utente.id, "tipi_turno", tipo_id, "cancellazione", f"etichetta={etichetta}")
    db.commit()
    imposta_flash(request, f'Tipo turno "{etichetta}" eliminato.', tipo="ok")
    return RedirectResponse("/tipi-turno", status_code=303)

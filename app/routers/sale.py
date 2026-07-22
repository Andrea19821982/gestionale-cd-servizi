"""Sale per eventi dentro i palazzi (es. Sala della Lupa a Montecitorio) e
gli eventi programmati al loro interno: quando una sala ha un evento in
corso, la copertura minima richiesta per il suo palazzo sale (vedi
app/routers/copertura.py: calcola_copertura)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_ANAGRAFICA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.logging_service import registra_modifica
from app.models import EventoSala, Sala, Sede, Utente
from app.templates import templates
from app.utils import checkbox_a_bool, ottieni_o_404

router = APIRouter()

# Limite di sicurezza per un evento ripetuto ogni settimana: evita che una
# data fine sbagliata (es. un anno digitato per errore) generi migliaia di
# righe invece delle poche decine attese.
MASSIMO_OCCORRENZE_RICORRENZA = 52


def _data_o_400(valore: str) -> date:
    try:
        return date.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data non valida: {valore!r}")


def _intero_non_negativo_o_400(valore: str) -> int:
    try:
        numero = int(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Valore non valido: {valore!r}")
    if numero < 0:
        raise HTTPException(status_code=400, detail="Il valore non può essere negativo.")
    return numero


@router.get("/sale")
def elenco_sale(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    sale = (
        db.query(Sala)
        .options(joinedload(Sala.sede))
        .join(Sede)
        .order_by(Sede.nome, Sala.nome)
        .all()
    )
    eventi = (
        db.query(EventoSala)
        .options(joinedload(EventoSala.sala).joinedload(Sala.sede))
        .filter(EventoSala.data_fine >= date.today())
        .order_by(EventoSala.data_inizio)
        .all()
    )
    sedi = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712
    return templates.TemplateResponse(
        request,
        "sale.html",
        {"sale": sale, "eventi": eventi, "sedi": sedi, "utente": utente},
    )


@router.post("/sale/nuova")
def crea_sala(
    request: Request,
    nome: str = Form(...),
    sede_id: int = Form(...),
    copertura_minima_aggiuntiva: str = Form(...),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    ottieni_o_404(db, Sede, sede_id)
    sala = Sala(
        nome=nome.strip(),
        sede_id=sede_id,
        copertura_minima_aggiuntiva=_intero_non_negativo_o_400(copertura_minima_aggiuntiva),
        attivo=True,
    )
    db.add(sala)
    db.flush()
    registra_modifica(db, utente.id, "sale", sala.id, "creazione", f"nome={sala.nome}, sede_id={sede_id}")
    db.commit()
    return RedirectResponse("/sale", status_code=303)


@router.post("/sale/{sala_id}/modifica")
def modifica_sala(
    request: Request,
    sala_id: int,
    nome: str = Form(...),
    sede_id: int = Form(...),
    copertura_minima_aggiuntiva: str = Form(...),
    attivo: str = Form(None),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    sala = ottieni_o_404(db, Sala, sala_id)
    ottieni_o_404(db, Sede, sede_id)
    sala.nome = nome.strip()
    sala.sede_id = sede_id
    sala.copertura_minima_aggiuntiva = _intero_non_negativo_o_400(copertura_minima_aggiuntiva)
    sala.attivo = checkbox_a_bool(attivo)
    registra_modifica(
        db, utente.id, "sale", sala.id, "modifica",
        f"nome={sala.nome}, sede_id={sede_id}, copertura_minima_aggiuntiva={sala.copertura_minima_aggiuntiva}, attivo={sala.attivo}",
    )
    db.commit()
    return RedirectResponse("/sale", status_code=303)


@router.post("/sale/eventi/nuovo")
def crea_evento_sala(
    request: Request,
    sala_id: int = Form(...),
    data_inizio: str = Form(...),
    data_fine: str = Form(...),
    descrizione: str = Form(""),
    ripeti_fino_al: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Senza ripeti_fino_al crea un solo evento (comportamento di sempre).
    Con ripeti_fino_al valorizzato, ripete lo stesso evento ogni settimana
    (stessa durata, stesso giorno della settimana) finché data_inizio non
    supera quella data: utile per sedute ricorrenti (es. ogni martedì) senza
    doverle registrare una per una."""
    ottieni_o_404(db, Sala, sala_id)
    inizio = _data_o_400(data_inizio)
    fine = _data_o_400(data_fine)
    if fine < inizio:
        raise HTTPException(status_code=400, detail="La data fine non può precedere la data inizio.")
    durata = fine - inizio
    descrizione_pulita = descrizione.strip() or None

    date_occorrenze = [inizio]
    if ripeti_fino_al:
        fino_al = _data_o_400(ripeti_fino_al)
        if fino_al < inizio:
            raise HTTPException(status_code=400, detail="La ripetizione non può finire prima dell'inizio del primo evento.")
        cursore = inizio
        while True:
            cursore += timedelta(days=7)
            if cursore > fino_al:
                break
            date_occorrenze.append(cursore)
            if len(date_occorrenze) > MASSIMO_OCCORRENZE_RICORRENZA:
                raise HTTPException(
                    status_code=400,
                    detail=f"Troppe occorrenze (oltre {MASSIMO_OCCORRENZE_RICORRENZA}): riduci l'intervallo di ripetizione.",
                )

    for inizio_occorrenza in date_occorrenze:
        evento = EventoSala(
            sala_id=sala_id,
            data_inizio=inizio_occorrenza,
            data_fine=inizio_occorrenza + durata,
            descrizione=descrizione_pulita,
            creato_da=utente.id,
        )
        db.add(evento)
        db.flush()
        registra_modifica(
            db, utente.id, "eventi_sala", evento.id, "creazione",
            f"sala_id={sala_id}, {evento.data_inizio.isoformat()}..{evento.data_fine.isoformat()}",
        )
    db.commit()
    return RedirectResponse("/sale", status_code=303)


@router.post("/sale/eventi/{evento_id}/elimina")
def elimina_evento_sala(
    evento_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    evento = ottieni_o_404(db, EventoSala, evento_id)
    sala_id = evento.sala_id
    db.delete(evento)
    registra_modifica(db, utente.id, "eventi_sala", evento_id, "cancellazione", f"sala_id={sala_id}")
    db.commit()
    return RedirectResponse("/sale", status_code=303)

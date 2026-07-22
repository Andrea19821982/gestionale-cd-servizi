"""Cruscotto "chi manca oggi in ogni sede": una vista rapida pensata per
capire subito dove serve una sostituzione, senza dover leggere il calendario
mensile cella per cella (backlog Zucchetti: cruscotto di copertura)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_LETTURA, richiedi_ruolo
from app.database import get_db
from app.models import AssegnazioneGiornaliera, Dipendente, EventoSala, Sala, Sede, Sostituzione, Utente
from app.templates import templates

router = APIRouter()


def _data_o_400(valore: str) -> date:
    try:
        return date.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data non valida: {valore!r}")


def calcola_copertura(db: Session, data_obj: date) -> list[dict]:
    """Per ogni sede attiva, chi dei suoi dipendenti di riferimento è
    presente/assente/non pianificato in quella data, più i sostituti in
    arrivo. Usata sia dal cruscotto interattivo qui sotto sia dal riepilogo
    giornaliero via email (vedi app/riepilogo_giornaliero.py): stessa
    identica logica in entrambi i posti, non una copia parallela."""
    sedi = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712
    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )
    assegnazioni = {
        r.dipendente_id: r
        for r in db.query(AssegnazioneGiornaliera)
        .options(joinedload(AssegnazioneGiornaliera.tipo_turno))
        .filter(AssegnazioneGiornaliera.data == data_obj)
        .all()
    }
    sostituzioni_in_arrivo = (
        db.query(Sostituzione)
        .options(joinedload(Sostituzione.dipendente_sostituto), joinedload(Sostituzione.dipendente_partente))
        .filter(Sostituzione.data == data_obj)
        .all()
    )
    sostituti_per_sede_arrivo = {}
    for s in sostituzioni_in_arrivo:
        sostituti_per_sede_arrivo.setdefault(s.sede_arrivo_id, []).append(s)

    eventi_in_corso = (
        db.query(EventoSala)
        .options(joinedload(EventoSala.sala))
        .join(Sala)
        .filter(
            Sala.attivo == True,  # noqa: E712
            EventoSala.data_inizio <= data_obj,
            EventoSala.data_fine >= data_obj,
        )
        .all()
    )
    eventi_per_sede = {}
    for evento in eventi_in_corso:
        eventi_per_sede.setdefault(evento.sala.sede_id, []).append(evento)

    blocchi = []
    for sede in sedi:
        righe = []
        presenti = 0
        for dip in dipendenti:
            if dip.sede_riferimento_id != sede.id:
                continue
            assegnazione = assegnazioni.get(dip.id)
            if assegnazione is None:
                stato = "non_pianificato"
            elif assegnazione.origine == "assenza":
                stato = "assente"
            elif assegnazione.tipo_turno_id is not None:
                stato = "presente"
                presenti += 1
            else:
                stato = "non_pianificato"
            righe.append({"dipendente": dip, "stato": stato, "assegnazione": assegnazione})

        eventi_sede = eventi_per_sede.get(sede.id, [])
        # Se più eventi in corso riguardano la stessa sala, la copertura
        # aggiuntiva di quella sala conta una sola volta (non si sommano
        # eventi sovrapposti nella stessa sala).
        sale_con_evento = {evento.sala_id: evento.sala for evento in eventi_sede}
        copertura_aggiuntiva = sum(sala.copertura_minima_aggiuntiva for sala in sale_con_evento.values())
        copertura_minima = sede.copertura_minima_ordinaria + copertura_aggiuntiva

        blocchi.append({
            "sede": sede,
            "righe": righe,
            "presenti": presenti,
            "totale": len(righe),
            "sostituti_in_arrivo": sostituti_per_sede_arrivo.get(sede.id, []),
            "eventi_oggi": eventi_sede,
            "copertura_minima": copertura_minima,
            "sotto_minimo": copertura_minima > 0 and presenti < copertura_minima,
        })

    # Per ogni palazzo sotto il minimo, suggerisce chi tra i dipendenti degli
    # ALTRI palazzi non è pianificato quel giorno: un punto di partenza per
    # trovare una sostituzione, non un'assegnazione automatica (chi gestisce
    # i turni resta libero di scegliere chi spostare davvero).
    non_pianificati_per_sede = {
        blocco["sede"].id: [riga["dipendente"] for riga in blocco["righe"] if riga["stato"] == "non_pianificato"]
        for blocco in blocchi
    }
    for blocco in blocchi:
        if not blocco["sotto_minimo"]:
            blocco["dipendenti_suggeriti"] = []
            continue
        blocco["dipendenti_suggeriti"] = [
            dip
            for sede_id, disponibili in non_pianificati_per_sede.items()
            if sede_id != blocco["sede"].id
            for dip in disponibili
        ]
    return blocchi


@router.get("/copertura")
def cruscotto_copertura(
    request: Request,
    data: str | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    data_obj = _data_o_400(data) if data else date.today()
    blocchi = calcola_copertura(db, data_obj)

    return templates.TemplateResponse(
        request,
        "copertura.html",
        {
            "utente": utente,
            "data": data_obj,
            "blocchi": blocchi,
        },
    )

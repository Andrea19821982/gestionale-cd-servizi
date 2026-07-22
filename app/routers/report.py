"""Report avanzato: andamento dell'assenteismo nel tempo e costo del lavoro
mensile (backlog Zucchetti). Riservato a chi gestisce operativamente
l'azienda: il costo orario è un dato sensibile, non lo vede la consultazione
né, ovviamente, il ruolo dipendente."""

from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.database import get_db
from app.models import Assenza, Dipendente, Utente
from app.routers.calendario import NOMI_MESE, _anno_mese_validi_o_oggi
from app.routers.statistiche import _ore_lavorate_nel_mese
from app.templates import templates

router = APIRouter()


def _giorni_assenza_azienda_nel_mese(db: Session, anno: int, mese: int) -> int:
    """Totale giorni di assenza approvata (tutti i dipendenti, tutti i tipi:
    ferie, malattia, permessi) che cadono in quel mese, per il trend annuale
    dell'assenteismo aziendale."""
    numero_giorni = monthrange(anno, mese)[1]
    inizio_mese = date(anno, mese, 1)
    fine_mese = date(anno, mese, numero_giorni)
    assenze = (
        db.query(Assenza)
        .filter(
            Assenza.stato == "approvata",
            Assenza.data_inizio <= fine_mese,
            Assenza.data_fine >= inizio_mese,
        )
        .all()
    )
    totale = 0
    for a in assenze:
        inizio_clip = max(a.data_inizio, inizio_mese)
        fine_clip = min(a.data_fine, fine_mese)
        totale += (fine_clip - inizio_clip).days + 1
    return totale


@router.get("/report")
def report(
    request: Request,
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    anno, mese = _anno_mese_validi_o_oggi(anno, mese)

    andamento_assenteismo = [
        {"mese": m, "mese_nome": NOMI_MESE[m], "giorni_assenza": _giorni_assenza_azienda_nel_mese(db, anno, m)}
        for m in range(1, 13)
    ]
    picco_assenteismo = max((r["giorni_assenza"] for r in andamento_assenteismo), default=0)

    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )
    righe_costo = []
    totale_costo_azienda = 0.0
    for dip in dipendenti:
        ore = _ore_lavorate_nel_mese(db, dip.id, anno, mese)
        costo_totale = round(ore * dip.costo_orario, 2) if dip.costo_orario is not None else None
        if costo_totale is not None:
            totale_costo_azienda += costo_totale
        righe_costo.append(
            {
                "dipendente": dip,
                "ore_lavorate": ore,
                "costo_orario": dip.costo_orario,
                "costo_totale": costo_totale,
            }
        )

    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "utente": utente,
            "anno": anno,
            "mese": mese,
            "mese_nome": NOMI_MESE[mese],
            "andamento_assenteismo": andamento_assenteismo,
            "picco_assenteismo": picco_assenteismo,
            "righe_costo": righe_costo,
            "totale_costo_azienda": round(totale_costo_azienda, 2),
        },
    )

"""Report avanzato: andamento dell'assenteismo nel tempo e costo del lavoro
mensile (backlog Zucchetti). Riservato a chi gestisce operativamente
l'azienda: il costo orario è un dato sensibile, non lo vede la consultazione
né, ovviamente, il ruolo dipendente."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.database import get_db
from app.models import Assenza, Dipendente, Utente
from app.routers.calendario import NOMI_MESE, _anno_mese_validi_o_oggi
from app.routers.statistiche import _ore_lavorate_nel_mese_per_dipendenti
from app.templates import templates

router = APIRouter()


def _giorni_assenza_azienda_per_mese_nell_anno(db: Session, anno: int) -> dict[int, int]:
    """Totale giorni di assenza approvata (tutti i dipendenti, tutti i tipi:
    ferie, malattia, permessi), per mese, per il trend annuale
    dell'assenteismo aziendale: un'unica query sull'intero anno invece di una
    per ciascuno dei 12 mesi, con il clip di ogni assenza sui mesi che tocca
    fatto in Python invece che a colpi di query ripetute per ogni mese."""
    inizio_anno = date(anno, 1, 1)
    fine_anno = date(anno, 12, 31)
    assenze = (
        db.query(Assenza)
        .filter(
            Assenza.stato == "approvata",
            Assenza.data_inizio <= fine_anno,
            Assenza.data_fine >= inizio_anno,
        )
        .all()
    )
    totali: dict[int, int] = defaultdict(int)
    for a in assenze:
        cursore = max(a.data_inizio, inizio_anno)
        fine_assenza = min(a.data_fine, fine_anno)
        while cursore <= fine_assenza:
            numero_giorni_mese = monthrange(cursore.year, cursore.month)[1]
            fine_mese = date(cursore.year, cursore.month, numero_giorni_mese)
            fine_clip = min(fine_assenza, fine_mese)
            totali[cursore.month] += (fine_clip - cursore).days + 1
            cursore = fine_mese + timedelta(days=1)
    return dict(totali)


@router.get("/report")
def report(
    request: Request,
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    anno, mese = _anno_mese_validi_o_oggi(anno, mese)

    giorni_assenza_per_mese = _giorni_assenza_azienda_per_mese_nell_anno(db, anno)
    andamento_assenteismo = [
        {"mese": m, "mese_nome": NOMI_MESE[m], "giorni_assenza": giorni_assenza_per_mese.get(m, 0)}
        for m in range(1, 13)
    ]
    picco_assenteismo = max((r["giorni_assenza"] for r in andamento_assenteismo), default=0)

    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )
    ore_lavorate_per_dip = _ore_lavorate_nel_mese_per_dipendenti(db, [d.id for d in dipendenti], anno, mese)
    righe_costo = []
    totale_costo_azienda = 0.0
    for dip in dipendenti:
        ore = ore_lavorate_per_dip.get(dip.id, 0.0)
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

"""Statistiche ore lavorate, ferie residue, sostituzioni fatte e storico
esiti di ferie/permessi (backlog di docs/02-requisiti.md).

Ferie residue: giorni_ferie_annuali del dipendente meno i giorni di assenza
di tipo "ferie" APPROVATI nell'anno solare scelto (i periodi a cavallo tra
due anni contano solo i giorni che cadono nell'anno selezionato). Richieste
in attesa o rifiutate non intaccano il monte ferie.

Ore lavorate: somma delle ore dei tipi turno assegnati (origine qualunque,
purché non un giorno di assenza) nel mese scelto.

Sostituzioni fatte / ferie e permessi concesse e rifiutate: conteggi
sull'anno scelto, per un riepilogo rapido; lo storico completo per un
singolo dipendente è nella sua scheda (/dipendenti/{id}/storico).
"""

from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_LETTURA, richiedi_ruolo
from app.database import get_db
from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Sostituzione, Utente
from app.routers.calendario import NOMI_MESE, _anno_mese_validi_o_oggi
from app.templates import templates

router = APIRouter()


def _ferie_annuali_effettive(dipendente: Dipendente) -> float:
    """Part-time: le ferie annuali (pensate per il tempo pieno) si riducono
    in proporzione alle ore settimanali del contratto rispetto a 40 ore."""
    return round(dipendente.giorni_ferie_annuali * dipendente.ore_settimanali_contrattuali / 40, 1)


def _ore_contrattuali_nel_mese(dipendente: Dipendente) -> float:
    """Ore mensili attese dal contratto, usando la media di 4,348 settimane
    al mese (52 settimane / 12 mesi): il termine di paragone per le ore
    lavorate, diverso per un part-time rispetto a un tempo pieno."""
    return round(dipendente.ore_settimanali_contrattuali * 4.348, 1)


def _giorni_ferie_usati_nell_anno(db: Session, dipendente_id: int, anno: int) -> int:
    inizio_anno = date(anno, 1, 1)
    fine_anno = date(anno, 12, 31)
    assenze_ferie = (
        db.query(Assenza)
        .filter(
            Assenza.dipendente_id == dipendente_id,
            Assenza.tipo_assenza.ilike("%ferie%"),
            Assenza.stato == "approvata",
            Assenza.data_inizio <= fine_anno,
            Assenza.data_fine >= inizio_anno,
        )
        .all()
    )
    totale = 0
    for assenza in assenze_ferie:
        inizio_clip = max(assenza.data_inizio, inizio_anno)
        fine_clip = min(assenza.data_fine, fine_anno)
        totale += (fine_clip - inizio_clip).days + 1
    return totale


def _ore_lavorate_nel_mese(db: Session, dipendente_id: int, anno: int, mese: int) -> float:
    numero_giorni = monthrange(anno, mese)[1]
    data_inizio = date(anno, mese, 1)
    data_fine = date(anno, mese, numero_giorni)
    righe = (
        db.query(AssegnazioneGiornaliera)
        .options(joinedload(AssegnazioneGiornaliera.tipo_turno))
        .filter(
            AssegnazioneGiornaliera.dipendente_id == dipendente_id,
            AssegnazioneGiornaliera.data >= data_inizio,
            AssegnazioneGiornaliera.data <= data_fine,
            AssegnazioneGiornaliera.tipo_turno_id.isnot(None),
        )
        .all()
    )
    totale_minuti = 0
    for riga in righe:
        turno = riga.tipo_turno
        inizio_minuti = turno.ora_inizio.hour * 60 + turno.ora_inizio.minute
        fine_minuti = turno.ora_fine.hour * 60 + turno.ora_fine.minute
        if fine_minuti <= inizio_minuti:
            fine_minuti += 24 * 60  # turno che attraversa la mezzanotte
        totale_minuti += fine_minuti - inizio_minuti
    return round(totale_minuti / 60, 1)


def _conta_assenze_per_stato(db: Session, dipendente_id: int, anno: int, stato: str) -> int:
    """Richieste di ferie/permesso/malattia iniziate nell'anno scelto, per
    stato: conta le richieste (decisioni), non i giorni."""
    inizio_anno = date(anno, 1, 1)
    fine_anno = date(anno, 12, 31)
    return (
        db.query(Assenza)
        .filter(
            Assenza.dipendente_id == dipendente_id,
            Assenza.stato == stato,
            Assenza.data_inizio >= inizio_anno,
            Assenza.data_inizio <= fine_anno,
        )
        .count()
    )


def _conta_sostituzioni_fatte(db: Session, dipendente_id: int, anno: int) -> int:
    """Quante volte il dipendente ha coperto qualcun altro (come sostituto)
    nell'anno scelto."""
    inizio_anno = date(anno, 1, 1)
    fine_anno = date(anno, 12, 31)
    return (
        db.query(Sostituzione)
        .filter(
            Sostituzione.dipendente_sostituto_id == dipendente_id,
            Sostituzione.data >= inizio_anno,
            Sostituzione.data <= fine_anno,
        )
        .count()
    )


@router.get("/statistiche")
def statistiche(
    request: Request,
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    anno, mese = _anno_mese_validi_o_oggi(anno, mese)

    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )

    righe = []
    for dipendente in dipendenti:
        ferie_usate = _giorni_ferie_usati_nell_anno(db, dipendente.id, anno)
        ferie_annuali_effettive = _ferie_annuali_effettive(dipendente)
        righe.append(
            {
                "dipendente": dipendente,
                "ferie_annuali_effettive": ferie_annuali_effettive,
                "ferie_usate": ferie_usate,
                "ferie_residue": ferie_annuali_effettive - ferie_usate,
                "ore_lavorate_mese": _ore_lavorate_nel_mese(db, dipendente.id, anno, mese),
                "ore_contrattuali_mese": _ore_contrattuali_nel_mese(dipendente),
                "sostituzioni_fatte": _conta_sostituzioni_fatte(db, dipendente.id, anno),
                "assenze_concesse": _conta_assenze_per_stato(db, dipendente.id, anno, "approvata"),
                "assenze_rifiutate": _conta_assenze_per_stato(db, dipendente.id, anno, "rifiutata"),
            }
        )

    return templates.TemplateResponse(
        request,
        "statistiche.html",
        {
            "righe": righe,
            "anno": anno,
            "mese": mese,
            "mese_nome": NOMI_MESE[mese],
            "nomi_mese": NOMI_MESE,
            "utente": utente,
        },
    )

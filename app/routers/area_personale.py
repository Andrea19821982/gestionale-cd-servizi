"""Accesso self-service per il ruolo "dipendente": un dipendente collegato a
un account di questo tipo vede solo il proprio calendario e il proprio
storico, in sola lettura — niente dati sugli altri colleghi (privacy) e
nessun pulsante di modifica."""

from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.auth import richiedi_ruolo
from app.database import get_db
from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Utente
from app.routers.calendario import NOMI_MESE, _anno_mese_validi_o_oggi, _giorni_del_mese, _mese_precedente, _mese_successivo
from app.routers.statistiche import _ferie_annuali_effettive, _giorni_ferie_usati_nell_anno, _ore_lavorate_nel_mese
from app.templates import templates

router = APIRouter()


@router.get("/area-personale")
def area_personale(
    request: Request,
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo("dipendente")),
):
    if utente.dipendente_collegato_id is None:
        raise HTTPException(
            status_code=400,
            detail="Il tuo account non è collegato a nessuna scheda dipendente: chiedi a un amministratore di collegarlo da /utenti.",
        )
    dipendente = db.get(Dipendente, utente.dipendente_collegato_id)
    if dipendente is None:
        raise HTTPException(status_code=404, detail="La scheda dipendente collegata non esiste più.")

    anno, mese = _anno_mese_validi_o_oggi(anno, mese)
    numero_giorni = monthrange(anno, mese)[1]
    giorni = _giorni_del_mese(anno, mese)

    righe = (
        db.query(AssegnazioneGiornaliera)
        .options(joinedload(AssegnazioneGiornaliera.tipo_turno), joinedload(AssegnazioneGiornaliera.sede_effettiva))
        .filter(
            AssegnazioneGiornaliera.dipendente_id == dipendente.id,
            AssegnazioneGiornaliera.data >= date(anno, mese, 1),
            AssegnazioneGiornaliera.data <= date(anno, mese, numero_giorni),
        )
        .all()
    )
    assegnazione_per_giorno = {r.data.day: r for r in righe}

    assenze = (
        db.query(Assenza)
        .filter(Assenza.dipendente_id == dipendente.id)
        .order_by(Assenza.data_inizio.desc())
        .all()
    )

    ferie_annuali_effettive = _ferie_annuali_effettive(dipendente)
    ferie_usate = _giorni_ferie_usati_nell_anno(db, dipendente.id, anno)

    anno_prec, mese_prec = _mese_precedente(anno, mese)
    anno_succ, mese_succ = _mese_successivo(anno, mese)

    return templates.TemplateResponse(
        request,
        "area_personale.html",
        {
            "utente": utente,
            "dipendente": dipendente,
            "anno": anno,
            "mese": mese,
            "mese_nome": NOMI_MESE[mese],
            "giorni": giorni,
            "assegnazione_per_giorno": assegnazione_per_giorno,
            "assenze": assenze,
            "ferie_annuali_effettive": ferie_annuali_effettive,
            "ferie_usate": ferie_usate,
            "ferie_residue": ferie_annuali_effettive - ferie_usate,
            "ore_lavorate_mese": _ore_lavorate_nel_mese(db, dipendente.id, anno, mese),
            "anno_prec": anno_prec,
            "mese_prec": mese_prec,
            "anno_succ": anno_succ,
            "mese_succ": mese_succ,
        },
    )

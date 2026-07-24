"""Accesso self-service per il ruolo "dipendente": un dipendente collegato a
un account di questo tipo vede solo il proprio calendario e il proprio
storico, in sola lettura — niente dati sugli altri colleghi (privacy) e
nessun pulsante di modifica."""

from calendar import monthrange
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.email_service import invia_notifica_asincrona
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Sostituzione, Utente
from app.routers.assenze import _copri_giorni_con_assenza, _data_o_400, _malattia, _si_sovrappone
from app.routers.calendario import NOMI_MESE, _anno_mese_validi_o_oggi, _giorni_del_mese, _mese_precedente, _mese_successivo
from app.routers.statistiche import _ferie_annuali_effettive, _giorni_ferie_usati_nell_anno, _ore_lavorate_nel_mese
from app.templates import templates

router = APIRouter()


def _dipendente_del_richiedente(db: Session, utente: Utente) -> Dipendente:
    """Il dipendente collegato all'account "dipendente" autenticato: usato
    per garantire che una richiesta di assenza self-service riguardi
    sempre e solo chi la fa, mai un dipendente_id arrivato dal form."""
    if utente.dipendente_collegato_id is None:
        raise HTTPException(
            status_code=400,
            detail="Il tuo account non è collegato a nessuna scheda dipendente: chiedi a un amministratore di collegarlo da /utenti.",
        )
    dipendente = db.get(Dipendente, utente.dipendente_collegato_id)
    if dipendente is None:
        raise HTTPException(status_code=404, detail="La scheda dipendente collegata non esiste più.")
    return dipendente


@router.get("/area-personale")
def area_personale(
    request: Request,
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo("dipendente")),
):
    dipendente = _dipendente_del_richiedente(db, utente)

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

    data_inizio_mese = date(anno, mese, 1)
    data_fine_mese = date(anno, mese, numero_giorni)

    # Una sostituzione non tocca la riga di AssegnazioneGiornaliera di chi
    # sostituisce (vedi crea_sostituzione in sostituzioni.py: crea solo un
    # record a parte), quindi senza queste due query il dipendente non
    # saprebbe dalla propria area, per esempio, che oggi deve andare in
    # un'altra sede a coprire un collega: qui sotto non ha accesso al
    # calendario generale (per privacy sui colleghi), quindi è l'unico
    # posto dove può scoprirlo.
    sostituzioni_come_sostituto_per_giorno = {
        r.data.day: r
        for r in db.query(Sostituzione)
        .options(joinedload(Sostituzione.dipendente_partente), joinedload(Sostituzione.sede_arrivo))
        .filter(
            Sostituzione.dipendente_sostituto_id == dipendente.id,
            Sostituzione.data >= data_inizio_mese,
            Sostituzione.data <= data_fine_mese,
        )
        .all()
    }
    sostituzioni_come_partente_per_giorno = {
        r.data.day: r
        for r in db.query(Sostituzione)
        .options(joinedload(Sostituzione.dipendente_sostituto))
        .filter(
            Sostituzione.dipendente_partente_id == dipendente.id,
            Sostituzione.data >= data_inizio_mese,
            Sostituzione.data <= data_fine_mese,
        )
        .all()
    }

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
            "sostituzioni_come_sostituto_per_giorno": sostituzioni_come_sostituto_per_giorno,
            "sostituzioni_come_partente_per_giorno": sostituzioni_come_partente_per_giorno,
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


@router.post("/area-personale/richiedi-assenza")
def richiedi_assenza(
    request: Request,
    data_inizio: str = Form(...),
    data_fine: str = Form(...),
    tipo_assenza: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo("dipendente")),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Un dipendente può richiedere da sé un'assenza per il proprio account:
    stesso flusso di /assenze/nuova gestito dall'amministrativo (stato
    "richiesta", copre subito il calendario in attesa di una decisione,
    tranne per "Malattia" che non richiede approvazione e nasce già
    approvata, vedi _malattia), ma qui il dipendente_id non arriva mai dal
    form — è sempre e solo quello collegato all'utente autenticato (vedi
    _dipendente_del_richiedente), così nessuno può richiedere un'assenza
    per conto di un collega."""
    dipendente = _dipendente_del_richiedente(db, utente)

    inizio = _data_o_400(data_inizio)
    fine = _data_o_400(data_fine)
    if fine < inizio:
        raise HTTPException(status_code=400, detail="La data fine non può precedere la data inizio.")
    tipo_assenza = tipo_assenza.strip()
    if not tipo_assenza:
        raise HTTPException(status_code=400, detail="Indica il tipo di assenza.")
    if _si_sovrappone(db, dipendente.id, inizio, fine):
        raise HTTPException(
            status_code=400,
            detail="Hai già un'assenza (in attesa o approvata) che si sovrappone a questo periodo.",
        )

    approvazione_automatica = _malattia(tipo_assenza)
    assenza = Assenza(
        dipendente_id=dipendente.id,
        data_inizio=inizio,
        data_fine=fine,
        tipo_assenza=tipo_assenza,
        stato="approvata" if approvazione_automatica else "richiesta",
        note=note.strip() or None,
        creato_da=utente.id,
    )
    if approvazione_automatica:
        assenza.deciso_il = datetime.now()
    db.add(assenza)
    db.flush()
    _copri_giorni_con_assenza(db, dipendente, inizio, fine)
    registra_modifica(
        db, utente.id, "assenze", assenza.id, "creazione",
        f"dipendente_id={dipendente.id}, {inizio.isoformat()}..{fine.isoformat()}, tipo={tipo_assenza}, "
        f"stato={'approvata' if approvazione_automatica else 'richiesta'} (richiesta dal dipendente in area personale)",
    )
    db.commit()

    invia_notifica_asincrona(
        f"Nuova richiesta di assenza: {dipendente.cognome} {dipendente.nome}",
        "email_assenza.html",
        {
            "dipendente_nome": f"{dipendente.cognome} {dipendente.nome}",
            "tipo_assenza": tipo_assenza,
            "data_inizio": inizio.isoformat(),
            "data_fine": fine.isoformat(),
            "esito": "Approvata automaticamente (malattia)" if approvazione_automatica else "Richiesta dal dipendente, in attesa di approvazione",
            "note": assenza.note,
            "registrato_da": f"{dipendente.cognome} {dipendente.nome} (richiesta da sé in area personale)",
        },
    )
    if approvazione_automatica:
        imposta_flash(request, "Assenza per malattia registrata e approvata automaticamente.", tipo="ok")
    else:
        imposta_flash(request, "Richiesta di assenza inviata: resterà in attesa di approvazione.", tipo="ok")
    return RedirectResponse("/area-personale", status_code=303)

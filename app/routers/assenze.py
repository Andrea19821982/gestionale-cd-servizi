import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_OPERATIVO, puo_approvare_assenze, richiedi_approvatore, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.email_service import invia_notifica_asincrona
from app.logging_service import registra_modifica
from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Utente
from app.paths import cartella_dati
from app.templates import templates
from app.utils import ottieni_o_404

router = APIRouter()

CARTELLA_ALLEGATI = cartella_dati() / "allegati"
ESTENSIONI_ALLEGATO_VALIDE = {".pdf", ".jpg", ".jpeg", ".png"}
DIMENSIONE_MASSIMA_ALLEGATO = 5 * 1024 * 1024  # 5 MB: certificati scansionati, non archivi


def _data_o_400(valore: str) -> date:
    try:
        return date.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data non valida: {valore!r}")


def _salva_allegato(assenza_id: int, allegato: UploadFile, contenuto: bytes) -> str:
    """Salva il file su disco con un nome generato (evita collisioni e
    problemi di path traversal) e restituisce il nome del file salvato."""
    estensione = Path(allegato.filename or "").suffix.lower()
    CARTELLA_ALLEGATI.mkdir(parents=True, exist_ok=True)
    nome_salvato = f"{assenza_id}_{uuid.uuid4().hex}{estensione}"
    (CARTELLA_ALLEGATI / nome_salvato).write_bytes(contenuto)
    return nome_salvato


def _si_sovrappone(db: Session, dipendente_id: int, inizio: date, fine: date, escludi_id: int | None = None) -> bool:
    """Controlla la sovrapposizione con qualunque assenza non rifiutata: una
    richiesta appena registrata occupa già il calendario (l'amministrativo la
    inserisce e il capo la valuta dopo), quindi conta come le approvate. Solo
    le rifiutate sono escluse, perché hanno liberato le celle che occupavano."""
    query = db.query(Assenza).filter(
        Assenza.dipendente_id == dipendente_id,
        Assenza.stato != "rifiutata",
        Assenza.data_inizio <= fine,
        Assenza.data_fine >= inizio,
    )
    if escludi_id is not None:
        query = query.filter(Assenza.id != escludi_id)
    return query.first() is not None


def _copri_giorni_con_assenza(db: Session, dipendente: Dipendente, inizio: date, fine: date) -> None:
    """L'assenza approvata disattiva il turno nei giorni che copre:
    sovrascrive qualunque assegnazione ci fosse (pattern o manuale), perché
    essere assenti prevale su quanto pianificato."""
    giorno = inizio
    while giorno <= fine:
        esistente = (
            db.query(AssegnazioneGiornaliera)
            .filter_by(dipendente_id=dipendente.id, data=giorno)
            .first()
        )
        if esistente is None:
            db.add(AssegnazioneGiornaliera(
                dipendente_id=dipendente.id,
                data=giorno,
                sede_effettiva_id=dipendente.sede_riferimento_id,
                tipo_turno_id=None,
                origine="assenza",
            ))
        else:
            esistente.tipo_turno_id = None
            esistente.sede_effettiva_id = dipendente.sede_riferimento_id
            esistente.origine = "assenza"
        giorno += timedelta(days=1)


def _scopri_giorni_assenza(db: Session, dipendente_id: int, inizio: date, fine: date) -> None:
    """Usata sia al rifiuto sia alla cancellazione: libera le celle che
    l'assenza aveva coperto (solo quelle con origine=assenza: non tocca
    eventuali altre assegnazioni non collegate a questa assenza)."""
    righe = (
        db.query(AssegnazioneGiornaliera)
        .filter(
            AssegnazioneGiornaliera.dipendente_id == dipendente_id,
            AssegnazioneGiornaliera.data >= inizio,
            AssegnazioneGiornaliera.data <= fine,
            AssegnazioneGiornaliera.origine == "assenza",
        )
        .all()
    )
    for riga in righe:
        db.delete(riga)


@router.get("/assenze")
def elenco_assenze(
    request: Request,
    dipendente_id: int | None = None,
    stato: str | None = None,
    data_da: str | None = None,
    data_a: str | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    query = db.query(Assenza)
    if dipendente_id:
        query = query.filter(Assenza.dipendente_id == dipendente_id)
    if stato:
        query = query.filter(Assenza.stato == stato)
    if data_da:
        query = query.filter(Assenza.data_fine >= _data_o_400(data_da))
    if data_a:
        query = query.filter(Assenza.data_inizio <= _data_o_400(data_a))
    assenze = query.order_by(Assenza.data_inizio.desc()).all()

    dipendenti = db.query(Dipendente).order_by(Dipendente.cognome, Dipendente.nome).all()

    return templates.TemplateResponse(
        request,
        "assenze.html",
        {
            "assenze": assenze,
            "dipendenti": dipendenti,
            "utente": utente,
            "puo_approvare": puo_approvare_assenze(db, utente),
            "filtri": {
                "dipendente_id": dipendente_id,
                "stato": stato or "",
                "data_da": data_da or "",
                "data_a": data_a or "",
            },
        },
    )


@router.post("/assenze/nuova")
def crea_assenza(
    dipendente_id: int = Form(...),
    data_inizio: str = Form(...),
    data_fine: str = Form(...),
    tipo_assenza: str = Form(...),
    note: str = Form(""),
    allegato: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Registra l'assenza segnalata dall'amministrativo: copre subito il
    calendario (chi la inserisce non è chi la approva, e nel frattempo il
    turno non va comunque coperto). Se il capo la rifiuterà in seguito, le
    celle coperte torneranno libere ma questa richiesta resterà nello storico."""
    dipendente = ottieni_o_404(db, Dipendente, dipendente_id)
    inizio = _data_o_400(data_inizio)
    fine = _data_o_400(data_fine)
    if fine < inizio:
        raise HTTPException(status_code=400, detail="La data fine non può precedere la data inizio.")
    tipo_assenza = tipo_assenza.strip()
    if not tipo_assenza:
        raise HTTPException(status_code=400, detail="Indica il tipo di assenza.")
    if _si_sovrappone(db, dipendente_id, inizio, fine):
        raise HTTPException(
            status_code=400,
            detail="Il dipendente ha già un'assenza (in attesa o approvata) che si sovrappone a questo periodo.",
        )

    contenuto_allegato = None
    if allegato is not None and allegato.filename:
        estensione = Path(allegato.filename).suffix.lower()
        if estensione not in ESTENSIONI_ALLEGATO_VALIDE:
            raise HTTPException(status_code=400, detail="Allegato non valido: sono ammessi solo PDF, JPG o PNG.")
        # Legge al massimo un byte oltre il limite: un file da centinaia di MB
        # non deve mai finire tutto in memoria solo per scoprire poi che è
        # troppo grande, il limite va rispettato già in lettura.
        contenuto_allegato = allegato.file.read(DIMENSIONE_MASSIMA_ALLEGATO + 1)
        if len(contenuto_allegato) > DIMENSIONE_MASSIMA_ALLEGATO:
            raise HTTPException(status_code=400, detail="Allegato troppo grande: massimo 5 MB.")

    assenza = Assenza(
        dipendente_id=dipendente_id,
        data_inizio=inizio,
        data_fine=fine,
        tipo_assenza=tipo_assenza,
        stato="richiesta",
        note=note.strip() or None,
        creato_da=utente.id,
    )
    db.add(assenza)
    db.flush()
    if contenuto_allegato is not None:
        assenza.allegato_nome = allegato.filename
        assenza.allegato_path = _salva_allegato(assenza.id, allegato, contenuto_allegato)
    _copri_giorni_con_assenza(db, dipendente, inizio, fine)
    registra_modifica(
        db, utente.id, "assenze", assenza.id, "creazione",
        f"dipendente_id={dipendente_id}, {inizio.isoformat()}..{fine.isoformat()}, tipo={tipo_assenza}, stato=richiesta",
    )
    db.commit()

    invia_notifica_asincrona(
        f"Nuova assenza registrata: {dipendente.cognome} {dipendente.nome}",
        "email_assenza.html",
        {
            "dipendente_nome": f"{dipendente.cognome} {dipendente.nome}",
            "tipo_assenza": tipo_assenza,
            "data_inizio": inizio.isoformat(),
            "data_fine": fine.isoformat(),
            "esito": "Registrata, in attesa di approvazione",
            "note": assenza.note,
            "registrato_da": utente.username,
        },
    )
    return RedirectResponse("/assenze", status_code=303)


@router.post("/assenze/{assenza_id}/approva")
def approva_assenza(
    assenza_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_approvatore),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    assenza = ottieni_o_404(db, Assenza, assenza_id)
    if assenza.stato != "richiesta":
        raise HTTPException(status_code=400, detail="Questa richiesta è già stata decisa.")

    dipendente = ottieni_o_404(db, Dipendente, assenza.dipendente_id)
    assenza.stato = "approvata"
    assenza.deciso_da = utente.id
    assenza.deciso_il = datetime.now()
    # Il calendario è già coperto dalla creazione della richiesta: qui si
    # ripete la copertura solo per sicurezza (idempotente), non perché serva.
    _copri_giorni_con_assenza(db, dipendente, assenza.data_inizio, assenza.data_fine)
    registra_modifica(
        db, utente.id, "assenze", assenza.id, "modifica",
        f"dipendente_id={assenza.dipendente_id}, stato=approvata",
    )
    db.commit()

    invia_notifica_asincrona(
        f"Richiesta di assenza approvata: {dipendente.cognome} {dipendente.nome}",
        "email_assenza.html",
        {
            "dipendente_nome": f"{dipendente.cognome} {dipendente.nome}",
            "tipo_assenza": assenza.tipo_assenza,
            "data_inizio": assenza.data_inizio.isoformat(),
            "data_fine": assenza.data_fine.isoformat(),
            "esito": "Approvata",
            "note": assenza.note,
            "registrato_da": utente.username,
        },
    )
    return RedirectResponse("/assenze", status_code=303)


@router.post("/assenze/{assenza_id}/rifiuta")
def rifiuta_assenza(
    assenza_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_approvatore),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    assenza = ottieni_o_404(db, Assenza, assenza_id)
    if assenza.stato != "richiesta":
        raise HTTPException(status_code=400, detail="Questa richiesta è già stata decisa.")

    dipendente = ottieni_o_404(db, Dipendente, assenza.dipendente_id)
    assenza.stato = "rifiutata"
    assenza.deciso_da = utente.id
    assenza.deciso_il = datetime.now()
    # La richiesta aveva già coperto il calendario alla creazione: il rifiuto
    # libera quelle celle, ma la riga Assenza resta come storico della
    # richiesta fatta e del rifiuto ricevuto (non viene mai cancellata qui).
    _scopri_giorni_assenza(db, assenza.dipendente_id, assenza.data_inizio, assenza.data_fine)
    registra_modifica(
        db, utente.id, "assenze", assenza.id, "modifica",
        f"dipendente_id={assenza.dipendente_id}, stato=rifiutata",
    )
    db.commit()

    invia_notifica_asincrona(
        f"Richiesta di assenza rifiutata: {dipendente.cognome} {dipendente.nome}",
        "email_assenza.html",
        {
            "dipendente_nome": f"{dipendente.cognome} {dipendente.nome}",
            "tipo_assenza": assenza.tipo_assenza,
            "data_inizio": assenza.data_inizio.isoformat(),
            "data_fine": assenza.data_fine.isoformat(),
            "esito": "Rifiutata",
            "note": assenza.note,
            "registrato_da": utente.username,
        },
    )
    return RedirectResponse("/assenze", status_code=303)


@router.get("/assenze/{assenza_id}/allegato")
def scarica_allegato_assenza(
    assenza_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    assenza = ottieni_o_404(db, Assenza, assenza_id)
    if not assenza.allegato_path:
        raise HTTPException(status_code=404, detail="Questa assenza non ha nessun allegato.")
    percorso = CARTELLA_ALLEGATI / assenza.allegato_path
    if not percorso.is_file():
        raise HTTPException(status_code=404, detail="File allegato non trovato sul disco.")
    return FileResponse(percorso, filename=assenza.allegato_nome or percorso.name)


@router.post("/assenze/{assenza_id}/elimina")
def elimina_assenza(
    assenza_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    assenza = ottieni_o_404(db, Assenza, assenza_id)
    dipendente_id, inizio, fine = assenza.dipendente_id, assenza.data_inizio, assenza.data_fine
    _scopri_giorni_assenza(db, dipendente_id, inizio, fine)
    if assenza.allegato_path:
        (CARTELLA_ALLEGATI / assenza.allegato_path).unlink(missing_ok=True)
    db.delete(assenza)
    registra_modifica(
        db, utente.id, "assenze", assenza_id, "cancellazione",
        f"dipendente_id={dipendente_id}, {inizio.isoformat()}..{fine.isoformat()}",
    )
    db.commit()
    return RedirectResponse("/assenze", status_code=303)

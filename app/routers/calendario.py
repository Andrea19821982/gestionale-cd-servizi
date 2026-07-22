from calendar import monthrange
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.logging_service import registra_modifica
from app.models import AssegnazioneGiornaliera, Dipendente, PatternTurno, Sede, Sostituzione, TipoTurno, Utente
from app.templates import templates
from app.utils import fk_opzionale_o_400, ottieni_o_404

router = APIRouter()

INIZIALI_GIORNO = ["L", "M", "M", "G", "V", "S", "D"]  # weekday(): 0=lunedì .. 6=domenica

NOMI_MESE = [
    "", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]

ANNO_MINIMO, ANNO_MASSIMO = 2000, 2100


def _mese_precedente(anno: int, mese: int) -> tuple[int, int]:
    return (anno - 1, 12) if mese == 1 else (anno, mese - 1)


def _mese_successivo(anno: int, mese: int) -> tuple[int, int]:
    return (anno + 1, 1) if mese == 12 else (anno, mese + 1)


def _anno_mese_validi_o_oggi(anno: int | None, mese: int | None) -> tuple[int, int]:
    """Per la vista in sola lettura: un anno/mese fuori range in un URL
    (bookmark vecchio, link modificato a mano) non deve far crashare la
    pagina con un 500 — si torna semplicemente al mese corrente."""
    oggi = date.today()
    if mese is None or not (1 <= mese <= 12):
        mese = oggi.month
    if anno is None or not (ANNO_MINIMO <= anno <= ANNO_MASSIMO):
        anno = oggi.year
    return anno, mese


def _anno_mese_validi_o_400(anno: int, mese: int) -> None:
    """Per le azioni che modificano dati: un mese/anno fuori range qui
    indica un form malformato o una richiesta diretta non passata dalla UI,
    quindi va rifiutata esplicitamente invece di essere corretta in silenzio."""
    if not (1 <= mese <= 12):
        raise HTTPException(status_code=400, detail=f"Mese non valido: {mese}")
    if not (ANNO_MINIMO <= anno <= ANNO_MASSIMO):
        raise HTTPException(status_code=400, detail=f"Anno non valido: {anno}")


def _assegnazione_esistente(db: Session, dipendente_id: int, data_obj: date) -> AssegnazioneGiornaliera | None:
    return (
        db.query(AssegnazioneGiornaliera)
        .filter_by(dipendente_id=dipendente_id, data=data_obj)
        .first()
    )


def _sostituzioni_cella(db: Session, dipendente_partente_id: int, data_obj: date) -> list[Sostituzione]:
    return (
        db.query(Sostituzione)
        .options(joinedload(Sostituzione.dipendente_sostituto).joinedload(Dipendente.sede_riferimento))
        .filter(
            Sostituzione.dipendente_partente_id == dipendente_partente_id,
            Sostituzione.data == data_obj,
        )
        .all()
    )


def _giorni_del_mese(anno: int, mese: int) -> list[dict]:
    numero_giorni = monthrange(anno, mese)[1]
    giorni = []
    for numero in range(1, numero_giorni + 1):
        d = date(anno, mese, numero)
        giorni.append(
            {"numero": numero, "iniziale": INIZIALI_GIORNO[d.weekday()], "weekend": d.weekday() >= 5}
        )
    return giorni


def _dati_calendario_sede(db: Session, sede: Sede, anno: int, mese: int, numero_giorni: int):
    """Dipendenti di una sede col loro calendario del mese: assegnazioni
    giornaliere e sostituzioni in arrivo, pronte per il rendering (usato sia
    dalla vista interattiva sia dalla vista di stampa)."""
    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.sede_riferimento_id == sede.id, Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.ordine_visualizzazione, Dipendente.cognome, Dipendente.nome)
        .all()
    )
    assegnazioni_per_dipendente = defaultdict(dict)
    sostituzioni_per_dipendente = defaultdict(lambda: defaultdict(list))
    if dipendenti:
        data_inizio = date(anno, mese, 1)
        data_fine = date(anno, mese, numero_giorni)
        id_dipendenti = [d.id for d in dipendenti]
        righe = (
            db.query(AssegnazioneGiornaliera)
            .options(joinedload(AssegnazioneGiornaliera.tipo_turno))
            .filter(
                AssegnazioneGiornaliera.dipendente_id.in_(id_dipendenti),
                AssegnazioneGiornaliera.data >= data_inizio,
                AssegnazioneGiornaliera.data <= data_fine,
            )
            .all()
        )
        for r in righe:
            assegnazioni_per_dipendente[r.dipendente_id][r.data.day] = r

        righe_sost = (
            db.query(Sostituzione)
            .options(joinedload(Sostituzione.dipendente_sostituto).joinedload(Dipendente.sede_riferimento))
            .filter(
                Sostituzione.dipendente_partente_id.in_(id_dipendenti),
                Sostituzione.data >= data_inizio,
                Sostituzione.data <= data_fine,
            )
            .all()
        )
        for r in righe_sost:
            sostituzioni_per_dipendente[r.dipendente_partente_id][r.data.day].append(r)

    return dipendenti, assegnazioni_per_dipendente, sostituzioni_per_dipendente


@router.get("/calendario")
def vista_calendario(
    request: Request,
    sede_id: int | None = None,
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    anno, mese = _anno_mese_validi_o_oggi(anno, mese)

    sedi = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712
    sede_corrente = (
        db.query(Sede).filter(Sede.id == sede_id, Sede.attivo == True).first()  # noqa: E712
        if sede_id
        else None
    )
    if sede_corrente is None and sedi:
        sede_corrente = sedi[0]

    numero_giorni = monthrange(anno, mese)[1]
    giorni = _giorni_del_mese(anno, mese)

    dipendenti = []
    assegnazioni_per_dipendente = defaultdict(dict)
    sostituzioni_per_dipendente = defaultdict(lambda: defaultdict(list))
    if sede_corrente:
        dipendenti, assegnazioni_per_dipendente, sostituzioni_per_dipendente = _dati_calendario_sede(
            db, sede_corrente, anno, mese, numero_giorni
        )

    anno_prec, mese_prec = _mese_precedente(anno, mese)
    anno_succ, mese_succ = _mese_successivo(anno, mese)
    tipi_turno = db.query(TipoTurno).order_by(TipoTurno.ora_inizio).all()

    return templates.TemplateResponse(
        request,
        "calendario.html",
        {
            "utente": utente,
            "sedi": sedi,
            "sede_corrente": sede_corrente,
            "anno": anno,
            "mese": mese,
            "mese_nome": NOMI_MESE[mese],
            "giorni": giorni,
            "dipendenti": dipendenti,
            "assegnazioni_per_dipendente": assegnazioni_per_dipendente,
            "sostituzioni_per_dipendente": sostituzioni_per_dipendente,
            "tipi_turno": tipi_turno,
            "anno_prec": anno_prec,
            "mese_prec": mese_prec,
            "anno_succ": anno_succ,
            "mese_succ": mese_succ,
        },
    )


@router.post("/calendario/genera")
def genera_da_pattern(
    sede_id: int = Form(...),
    anno: int = Form(...),
    mese: int = Form(...),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Genera la proposta di calendario del mese per una sede a partire dal
    pattern settimana dispari/pari di ciascun dipendente. Non tocca i giorni
    che hanno già un'assegnazione (manuale, da sostituzione o da assenza):
    tocca solo le celle ancora vuote."""
    _anno_mese_validi_o_400(anno, mese)
    ottieni_o_404(db, Sede, sede_id)
    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.sede_riferimento_id == sede_id, Dipendente.attivo == True)  # noqa: E712
        .all()
    )
    numero_giorni = monthrange(anno, mese)[1]
    creati = 0

    for dip in dipendenti:
        pattern = db.get(PatternTurno, dip.id)
        if pattern is None:
            continue
        for giorno in range(1, numero_giorni + 1):
            d = date(anno, mese, giorno)
            settimana_dispari = d.isocalendar().week % 2 == 1
            tipo_id = (
                pattern.turno_settimana_dispari_id
                if settimana_dispari
                else pattern.turno_settimana_pari_id
            )
            if tipo_id is None:
                continue
            if _assegnazione_esistente(db, dip.id, d) is not None:
                continue
            db.add(
                AssegnazioneGiornaliera(
                    dipendente_id=dip.id,
                    data=d,
                    sede_effettiva_id=dip.sede_riferimento_id,
                    tipo_turno_id=tipo_id,
                    origine="pattern",
                )
            )
            creati += 1

    if creati:
        registra_modifica(
            db, utente.id, "assegnazioni_giornaliere", sede_id, "creazione",
            f"generazione da pattern: sede_id={sede_id}, {anno}-{mese:02d}, {creati} celle create",
        )
    try:
        db.commit()
    except IntegrityError:
        # Un'altra richiesta concorrente ha generato le stesse celle nel
        # frattempo: non è un errore da mostrare all'utente, il risultato
        # a schermo (ricaricato dal redirect) è comunque corretto.
        db.rollback()
    return RedirectResponse(f"/calendario?sede_id={sede_id}&anno={anno}&mese={mese}", status_code=303)


@router.post("/calendario/cella")
def salva_cella(
    request: Request,
    dipendente_id: int = Form(...),
    data: str = Form(...),
    tipo_turno_id: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Modifica manuale di una singola cella: sovrascrive sempre con
    origine=manuale, indipendentemente da cosa c'era prima (pattern,
    sostituzione o assenza), perché è un intervento diretto di chi pianifica."""
    dipendente = ottieni_o_404(db, Dipendente, dipendente_id)
    try:
        data_obj = date.fromisoformat(data)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data non valida: {data!r}")
    tipo_id = fk_opzionale_o_400(db, TipoTurno, tipo_turno_id)

    if tipo_id is not None and dipendente.sede_riferimento_id is None:
        raise HTTPException(
            status_code=400,
            detail="Il dipendente non ha una sede di riferimento: assegnala prima di pianificare un turno.",
        )

    assegnazione = _assegnazione_esistente(db, dipendente_id, data_obj)

    if tipo_id is None:
        if assegnazione is not None:
            record_id = assegnazione.id
            db.delete(assegnazione)
            registra_modifica(
                db, utente.id, "assegnazioni_giornaliere", record_id, "cancellazione",
                f"dipendente_id={dipendente_id}, data={data}",
            )
        assegnazione = None
    elif assegnazione is None:
        assegnazione = AssegnazioneGiornaliera(
            dipendente_id=dipendente_id,
            data=data_obj,
            sede_effettiva_id=dipendente.sede_riferimento_id,
            tipo_turno_id=tipo_id,
            origine="manuale",
        )
        db.add(assegnazione)
        try:
            db.flush()
        except IntegrityError:
            # Un'altra richiesta ha creato la stessa cella un istante prima:
            # non è un conflitto da mostrare all'utente, si applica la sua
            # scelta come modifica sopra quella riga appena apparsa.
            db.rollback()
            assegnazione = _assegnazione_esistente(db, dipendente_id, data_obj)
            assegnazione.tipo_turno_id = tipo_id
            assegnazione.sede_effettiva_id = dipendente.sede_riferimento_id
            assegnazione.origine = "manuale"
            registra_modifica(
                db, utente.id, "assegnazioni_giornaliere", assegnazione.id, "modifica",
                f"dipendente_id={dipendente_id}, data={data}, tipo_turno_id={tipo_id}, origine=manuale",
            )
        else:
            registra_modifica(
                db, utente.id, "assegnazioni_giornaliere", assegnazione.id, "creazione",
                f"dipendente_id={dipendente_id}, data={data}, tipo_turno_id={tipo_id}, origine=manuale",
            )
    else:
        assegnazione.tipo_turno_id = tipo_id
        assegnazione.sede_effettiva_id = dipendente.sede_riferimento_id
        assegnazione.origine = "manuale"
        registra_modifica(
            db, utente.id, "assegnazioni_giornaliere", assegnazione.id, "modifica",
            f"dipendente_id={dipendente_id}, data={data}, tipo_turno_id={tipo_id}, origine=manuale",
        )

    db.commit()

    tipi_turno = db.query(TipoTurno).order_by(TipoTurno.ora_inizio).all()
    sostituzioni_giorno = _sostituzioni_cella(db, dipendente_id, data_obj)
    return templates.TemplateResponse(
        request,
        "_cella_calendario.html",
        {
            "dipendente": dipendente,
            "data_iso": data,
            "weekend": data_obj.weekday() >= 5,
            "assegnazione": assegnazione,
            "sostituzioni_giorno": sostituzioni_giorno,
            "tipi_turno": tipi_turno,
            "utente": utente,
        },
    )


@router.get("/calendario/stampa")
def stampa_calendario(
    request: Request,
    sede_id: int | None = None,
    tutte: bool = False,
    anno: int | None = None,
    mese: int | None = None,
    auto: bool = False,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    """Vista pensata per la stampa/esportazione PDF dal browser (Ctrl+P /
    'Salva come PDF'): sempre in sola lettura, indipendentemente dal ruolo di
    chi la apre, una sede per pagina se 'tutte' è richiesto. auto=1 (pulsante
    "Stampa" dedicato) apre subito la finestra di stampa; senza, l'utente
    vede prima l'anteprima e stampa/salva quando vuole (pulsante "Esporta PDF")."""
    anno, mese = _anno_mese_validi_o_oggi(anno, mese)
    numero_giorni = monthrange(anno, mese)[1]
    giorni = _giorni_del_mese(anno, mese)

    if tutte:
        sedi_da_stampare = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712
    else:
        sede = (
            db.query(Sede).filter(Sede.id == sede_id, Sede.attivo == True).first()  # noqa: E712
            if sede_id
            else db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).first()  # noqa: E712
        )
        sedi_da_stampare = [sede] if sede else []

    blocchi = []
    for sede in sedi_da_stampare:
        dipendenti, assegnazioni_per_dipendente, sostituzioni_per_dipendente = _dati_calendario_sede(
            db, sede, anno, mese, numero_giorni
        )
        blocchi.append(
            {
                "sede": sede,
                "dipendenti": dipendenti,
                "assegnazioni_per_dipendente": assegnazioni_per_dipendente,
                "sostituzioni_per_dipendente": sostituzioni_per_dipendente,
            }
        )

    return templates.TemplateResponse(
        request,
        "calendario_stampa.html",
        {
            "blocchi": blocchi,
            "giorni": giorni,
            "anno": anno,
            "mese": mese,
            "mese_nome": NOMI_MESE[mese],
            "tipi_turno": [],
            "utente": {"ruolo": "consultazione"},
            "auto": auto,
        },
    )

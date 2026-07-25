from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import Assenza, Dipendente, PatternTurno, Sede, Sostituzione, TipoTurno, Utente
from app.routers.statistiche import _ferie_annuali_effettive
from app.templates import templates
from app.utils import checkbox_a_bool, fk_opzionale_o_400, ottieni_o_404

router = APIRouter()


def _costo_orario_o_400(valore: str) -> float | None:
    """Stringa vuota -> nessun costo impostato (facoltativo). Un valore non
    numerico digitato per errore deve dare un 400 chiaro, non un 500 non
    gestito da un ValueError lasciato propagare."""
    valore = (valore or "").strip()
    if not valore:
        return None
    try:
        numero = float(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Costo orario non valido: {valore!r}")
    if numero < 0:
        raise HTTPException(status_code=400, detail="Il costo orario non può essere negativo.")
    return numero


def _ore_settimanali_o_400(valore: float) -> float:
    if not (0 < valore <= 168):
        raise HTTPException(status_code=400, detail="Le ore settimanali contrattuali devono essere tra 0 (escluso) e 168.")
    return valore


def _email_o_400(valore: str) -> str | None:
    valore = (valore or "").strip()
    if not valore:
        return None
    utente, _, dominio = valore.partition("@")
    if not utente or "." not in dominio or dominio.startswith(".") or dominio.endswith("."):
        raise HTTPException(status_code=400, detail=f"Indirizzo email non valido: {valore!r}")
    return valore


@router.get("/dipendenti")
def elenco_dipendenti(
    request: Request,
    solo_attivi: bool = False,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    query = db.query(Dipendente)
    if solo_attivi:
        query = query.filter(Dipendente.attivo == True)  # noqa: E712
    dipendenti = query.order_by(
        Dipendente.ordine_visualizzazione, Dipendente.cognome, Dipendente.nome
    ).all()
    sedi = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712
    return templates.TemplateResponse(
        request,
        "dipendenti.html",
        {
            "dipendenti": dipendenti,
            "sedi": sedi,
            "solo_attivi": solo_attivi,
            "utente": utente,
        },
    )


@router.post("/dipendenti/nuovo")
def crea_dipendente(
    request: Request,
    cognome: str = Form(...),
    nome: str = Form(...),
    sede_riferimento_id: str = Form(""),
    ordine_visualizzazione: int = Form(0),
    giorni_ferie_annuali: int = Form(26),
    tipo_contratto: str = Form(""),
    ore_settimanali_contrattuali: float = Form(40.0),
    costo_orario: str = Form(""),
    sottosezione: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    dipendente = Dipendente(
        cognome=cognome.strip(),
        nome=nome.strip(),
        sede_riferimento_id=fk_opzionale_o_400(db, Sede, sede_riferimento_id),
        ordine_visualizzazione=ordine_visualizzazione,
        giorni_ferie_annuali=giorni_ferie_annuali,
        tipo_contratto=tipo_contratto.strip() or None,
        ore_settimanali_contrattuali=_ore_settimanali_o_400(ore_settimanali_contrattuali),
        costo_orario=_costo_orario_o_400(costo_orario),
        sottosezione=sottosezione.strip() or None,
        email=_email_o_400(email),
        attivo=True,
    )
    db.add(dipendente)
    db.flush()
    registra_modifica(
        db, utente.id, "dipendenti", dipendente.id, "creazione",
        f"cognome={dipendente.cognome}, nome={dipendente.nome}",
    )
    db.commit()
    return RedirectResponse("/dipendenti", status_code=303)


@router.get("/dipendenti/{dipendente_id}/modifica")
def modifica_dipendente_form(
    request: Request,
    dipendente_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    """Pagina intera dedicata alla modifica (non più un pannello a comparsa
    dentro la riga della tabella /dipendenti: con tutti i campi di anagrafica
    più il pattern turno, in un riquadro stretto dentro la tabella non c'era
    mai spazio a sufficienza per non far andare tutto a capo su una colonna
    stretta, anche allargando il riquadro stesso — qui ha semplicemente
    tutta la pagina a disposizione, stesso approccio già usato per
    /tipi-turno e le altre pagine di anagrafica)."""
    dipendente = ottieni_o_404(db, Dipendente, dipendente_id)
    sedi = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712
    tipi_turno = db.query(TipoTurno).order_by(TipoTurno.ora_inizio).all()
    pattern = db.get(PatternTurno, dipendente_id)
    return templates.TemplateResponse(
        request,
        "dipendente_modifica.html",
        {
            "dipendente": dipendente,
            "sedi": sedi,
            "tipi_turno": tipi_turno,
            "pattern": pattern,
            "utente": utente,
        },
    )


@router.post("/dipendenti/{dipendente_id}/modifica")
def modifica_dipendente(
    request: Request,
    dipendente_id: int,
    cognome: str = Form(...),
    nome: str = Form(...),
    sede_riferimento_id: str = Form(""),
    ordine_visualizzazione: int = Form(0),
    giorni_ferie_annuali: int = Form(26),
    tipo_contratto: str = Form(""),
    ore_settimanali_contrattuali: float = Form(40.0),
    costo_orario: str = Form(""),
    sottosezione: str = Form(""),
    email: str = Form(""),
    attivo: str = Form(None),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    dipendente = ottieni_o_404(db, Dipendente, dipendente_id)
    era_attivo = dipendente.attivo
    dipendente.cognome = cognome.strip()
    dipendente.nome = nome.strip()
    dipendente.sede_riferimento_id = fk_opzionale_o_400(db, Sede, sede_riferimento_id)
    dipendente.ordine_visualizzazione = ordine_visualizzazione
    dipendente.giorni_ferie_annuali = giorni_ferie_annuali
    dipendente.tipo_contratto = tipo_contratto.strip() or None
    dipendente.ore_settimanali_contrattuali = _ore_settimanali_o_400(ore_settimanali_contrattuali)
    dipendente.costo_orario = _costo_orario_o_400(costo_orario)
    dipendente.sottosezione = sottosezione.strip() or None
    dipendente.email = _email_o_400(email)
    dipendente.attivo = checkbox_a_bool(attivo)
    registra_modifica(
        db, utente.id, "dipendenti", dipendente.id, "modifica",
        f"cognome={dipendente.cognome}, nome={dipendente.nome}, attivo={dipendente.attivo}",
    )
    db.commit()

    if era_attivo and not dipendente.attivo:
        account_collegato = (
            db.query(Utente)
            .filter(Utente.dipendente_collegato_id == dipendente.id, Utente.attivo == True)  # noqa: E712
            .first()
        )
        if account_collegato is not None:
            imposta_flash(
                request,
                f"Il dipendente {dipendente.cognome} {dipendente.nome} è stato disattivato, ma l'account "
                f"di accesso \"{account_collegato.username}\" ad esso collegato è ancora attivo: valuta se "
                f"disattivare anche quello da Utenti.",
                tipo="avviso",
            )
    else:
        imposta_flash(request, "Anagrafica aggiornata.", tipo="ok")

    return RedirectResponse(f"/dipendenti/{dipendente_id}/modifica", status_code=303)


@router.post("/dipendenti/{dipendente_id}/pattern")
def imposta_pattern_turno(
    request: Request,
    dipendente_id: int,
    turno_settimana_dispari_id: str = Form(""),
    turno_settimana_pari_id: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    ottieni_o_404(db, Dipendente, dipendente_id)
    dispari = fk_opzionale_o_400(db, TipoTurno, turno_settimana_dispari_id)
    pari = fk_opzionale_o_400(db, TipoTurno, turno_settimana_pari_id)

    pattern = db.get(PatternTurno, dipendente_id)
    if pattern is None:
        pattern = PatternTurno(
            dipendente_id=dipendente_id,
            turno_settimana_dispari_id=dispari,
            turno_settimana_pari_id=pari,
        )
        db.add(pattern)
        azione = "creazione"
    else:
        pattern.turno_settimana_dispari_id = dispari
        pattern.turno_settimana_pari_id = pari
        azione = "modifica"

    registra_modifica(
        db, utente.id, "pattern_turno", dipendente_id, azione,
        f"turno_settimana_dispari_id={dispari}, turno_settimana_pari_id={pari}",
    )
    db.commit()
    imposta_flash(request, "Pattern turno aggiornato.", tipo="ok")
    return RedirectResponse(f"/dipendenti/{dipendente_id}/modifica", status_code=303)


@router.get("/dipendenti/{dipendente_id}/storico")
def storico_dipendente(
    request: Request,
    dipendente_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    """Scheda completa di un dipendente: anagrafica, contratto, pattern
    turno e tutto lo storico che lo riguarda (ferie/permessi con il loro
    esito, sostituzioni fatte e ricevute)."""
    dipendente = ottieni_o_404(db, Dipendente, dipendente_id)
    pattern = db.get(PatternTurno, dipendente_id)

    assenze = (
        db.query(Assenza)
        .filter(Assenza.dipendente_id == dipendente_id)
        .order_by(Assenza.data_inizio.desc())
        .all()
    )
    sostituzioni_come_partente = (
        db.query(Sostituzione)
        .options(joinedload(Sostituzione.dipendente_sostituto), joinedload(Sostituzione.sede_arrivo))
        .filter(Sostituzione.dipendente_partente_id == dipendente_id)
        .order_by(Sostituzione.data.desc())
        .all()
    )
    sostituzioni_come_sostituto = (
        db.query(Sostituzione)
        .options(joinedload(Sostituzione.dipendente_partente), joinedload(Sostituzione.sede_partenza))
        .filter(Sostituzione.dipendente_sostituto_id == dipendente_id)
        .order_by(Sostituzione.data.desc())
        .all()
    )

    return templates.TemplateResponse(
        request,
        "dipendente_storico.html",
        {
            "dipendente": dipendente,
            "ferie_annuali_effettive": _ferie_annuali_effettive(dipendente),
            "pattern": pattern,
            "assenze": assenze,
            "sostituzioni_come_partente": sostituzioni_come_partente,
            "sostituzioni_come_sostituto": sostituzioni_come_sostituto,
            "utente": utente,
        },
    )

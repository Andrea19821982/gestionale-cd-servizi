import re
import unicodedata
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_SCRITTURA_ANAGRAFICA, hash_password, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.logging_service import registra_modifica
from app.models import DelegaApprovazione, Dipendente, RUOLI_VALIDI, Utente
from app.templates import templates
from app.utils import checkbox_a_bool, fk_opzionale_o_400, ottieni_o_404

router = APIRouter()


def _senza_accenti(testo: str) -> str:
    scomposto = unicodedata.normalize("NFKD", testo)
    return "".join(c for c in scomposto if not unicodedata.combining(c))


def _username_libero(db: Session, dipendente: Dipendente) -> str:
    """Uno username proponibile per questo dipendente, del tipo
    "rossi.mario", già verificato che non sia in uso.

    È solo una proposta scritta nel modulo: chi crea l'accesso può
    cambiarla prima di salvare. Serve a non doverla inventare nove volte di
    fila restando coerenti."""
    base = ".".join(
        parte for parte in (
            re.sub(r"[^a-z0-9]", "", _senza_accenti(dipendente.cognome).lower()),
            re.sub(r"[^a-z0-9]", "", _senza_accenti(dipendente.nome).lower()),
        ) if parte
    ) or f"dipendente{dipendente.id}"

    candidato = base
    contatore = 2
    while db.query(Utente).filter(Utente.username == candidato).first() is not None:
        candidato = f"{base}{contatore}"
        contatore += 1
    return candidato


@router.get("/utenti")
def elenco_utenti(
    request: Request,
    tutte_le_deleghe: bool = False,
    nuovo_per: int | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
):
    utenti = db.query(Utente).order_by(Utente.username).all()
    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )
    # Chi non ha ancora un accesso proprio: senza questo elenco, per dare
    # l'accesso a un gruppo di persone bisogna ricordarsi a memoria chi si è
    # già fatto e cercarlo ogni volta nella tendina di tutti i dipendenti.
    collegati = {u.dipendente_collegato_id for u in utenti if u.dipendente_collegato_id}
    dipendenti_senza_accesso = [d for d in dipendenti if d.id not in collegati]

    da_precompilare = db.get(Dipendente, nuovo_per) if nuovo_per else None
    username_suggerito = (
        _username_libero(db, da_precompilare) if da_precompilare is not None else ""
    )
    query_deleghe = db.query(DelegaApprovazione).options(joinedload(DelegaApprovazione.utente_delegato))
    if not tutte_le_deleghe:
        # Di default nasconde le deleghe già scadute: altrimenti la lista
        # cresce all'infinito e nasconde quelle davvero rilevanti (attive o
        # future). Restano comunque consultabili con "mostra tutte".
        query_deleghe = query_deleghe.filter(DelegaApprovazione.data_fine >= date.today())
    deleghe = query_deleghe.order_by(DelegaApprovazione.data_inizio.desc()).all()
    return templates.TemplateResponse(
        request,
        "utenti.html",
        {
            "utenti": utenti,
            "dipendenti": dipendenti,
            "dipendenti_senza_accesso": dipendenti_senza_accesso,
            "da_precompilare": da_precompilare,
            "username_suggerito": username_suggerito,
            "deleghe": deleghe,
            "tutte_le_deleghe": tutte_le_deleghe,
            "ruoli_validi": RUOLI_VALIDI,
            "oggi": date.today(),
            "utente": utente,
        },
    )


@router.post("/utenti/nuovo")
def crea_utente(
    username: str = Form(...),
    password: str = Form(...),
    ruolo: str = Form(...),
    dipendente_collegato_id: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Indica uno username.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri.")
    if ruolo not in RUOLI_VALIDI:
        raise HTTPException(status_code=400, detail=f"Ruolo non valido: {ruolo!r}")
    if db.query(Utente).filter(Utente.username == username).first() is not None:
        raise HTTPException(status_code=400, detail="Username già in uso.")

    nuovo = Utente(
        username=username,
        password_hash=hash_password(password),
        ruolo=ruolo,
        dipendente_collegato_id=fk_opzionale_o_400(db, Dipendente, dipendente_collegato_id),
        attivo=True,
    )
    db.add(nuovo)
    db.flush()
    registra_modifica(
        db, utente.id, "utenti", nuovo.id, "creazione",
        f"username={username}, ruolo={ruolo}",
    )
    db.commit()
    return RedirectResponse("/utenti", status_code=303)


@router.post("/utenti/{utente_id}/modifica")
def modifica_utente(
    utente_id: int,
    ruolo: str = Form(...),
    dipendente_collegato_id: str = Form(""),
    attivo: str = Form(None),
    nuova_password: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    da_modificare = ottieni_o_404(db, Utente, utente_id)
    if ruolo not in RUOLI_VALIDI:
        raise HTTPException(status_code=400, detail=f"Ruolo non valido: {ruolo!r}")
    if da_modificare.id == utente.id and (ruolo != "amministratore" or not checkbox_a_bool(attivo)):
        raise HTTPException(
            status_code=400,
            detail="Non puoi cambiare il tuo stesso ruolo o disattivare il tuo stesso account: "
            "fallo fare a un altro amministratore, per non restare bloccato fuori dal pannello.",
        )

    da_modificare.ruolo = ruolo
    da_modificare.dipendente_collegato_id = fk_opzionale_o_400(db, Dipendente, dipendente_collegato_id)
    da_modificare.attivo = checkbox_a_bool(attivo)
    if nuova_password:
        if len(nuova_password) < 8:
            raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri.")
        da_modificare.password_hash = hash_password(nuova_password)

    registra_modifica(
        db, utente.id, "utenti", da_modificare.id, "modifica",
        f"ruolo={ruolo}, attivo={da_modificare.attivo}",
    )
    db.commit()
    return RedirectResponse("/utenti", status_code=303)


@router.post("/deleghe/nuova")
def crea_delega(
    utente_delegato_id: int = Form(...),
    data_inizio: str = Form(...),
    data_fine: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    delegato = ottieni_o_404(db, Utente, utente_delegato_id)
    if delegato.ruolo == "dipendente":
        raise HTTPException(status_code=400, detail="Un account con ruolo dipendente non può ricevere una delega di approvazione.")
    try:
        inizio = date.fromisoformat(data_inizio)
        fine = date.fromisoformat(data_fine)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data non valida.")
    if fine < inizio:
        raise HTTPException(status_code=400, detail="La data fine non può precedere la data inizio.")

    delega = DelegaApprovazione(
        utente_delegato_id=utente_delegato_id,
        data_inizio=inizio,
        data_fine=fine,
        note=note.strip() or None,
        creato_da=utente.id,
    )
    db.add(delega)
    db.flush()
    registra_modifica(
        db, utente.id, "deleghe_approvazione", delega.id, "creazione",
        f"utente_delegato_id={utente_delegato_id}, {inizio.isoformat()}..{fine.isoformat()}",
    )
    db.commit()
    return RedirectResponse("/utenti", status_code=303)


@router.post("/deleghe/{delega_id}/elimina")
def elimina_delega(
    delega_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    delega = ottieni_o_404(db, DelegaApprovazione, delega_id)
    db.delete(delega)
    registra_modifica(db, utente.id, "deleghe_approvazione", delega_id, "cancellazione", "")
    db.commit()
    return RedirectResponse("/utenti", status_code=303)

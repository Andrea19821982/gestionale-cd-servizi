from datetime import date, time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.email_service import invia_notifica_asincrona
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import Dipendente, Sede, Sostituzione, Utente
from app.routers.assenze import _si_sovrappone
from app.templates import templates
from app.utils import ottieni_o_404

router = APIRouter()


def _data_o_400(valore: str) -> date:
    try:
        return date.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data non valida: {valore!r}")


def _ora_opzionale_o_400(valore: str) -> time | None:
    if not valore:
        return None
    try:
        return time.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Orario non valido: {valore!r}")


def _sostituzione_in_conflitto(
    db: Session,
    dipendente_partente_id: int,
    data_sost: date,
    inizio: time | None,
    fine: time | None,
) -> bool:
    """Controlla se per lo stesso dipendente, nello stesso giorno, esiste già
    una sostituzione che si sovrappone a quella che si vuole creare (None,None
    = intera giornata). Un'intera giornata è in conflitto con qualunque altra
    sostituzione di quel giorno (copre già tutte le ore, chiunque sia
    l'altro sostituto); due sostituzioni orarie sono in conflitto solo se le
    loro fasce si sovrappongono davvero (09-11 e 11-13 non si toccano, quindi
    vanno bene entrambe): altrimenti due sostituti diversi finirebbero per
    coprire contemporaneamente lo stesso dipendente nella stessa fascia."""
    esistenti = (
        db.query(Sostituzione)
        .filter(
            Sostituzione.dipendente_partente_id == dipendente_partente_id,
            Sostituzione.data == data_sost,
        )
        .all()
    )
    for esistente in esistenti:
        if inizio is None or esistente.ora_inizio is None:
            return True
        if esistente.ora_inizio < fine and esistente.ora_fine > inizio:
            return True
    return False


def _sostituto_non_disponibile(
    db: Session,
    dipendente_sostituto_id: int,
    data_sost: date,
    inizio: time | None,
    fine: time | None,
) -> str | None:
    """Motivo per cui il sostituto scelto non può coprire, o None se è
    libero. Restituisce già la frase da mostrare: i due motivi vanno
    spiegati in modo diverso a chi sta compilando il form.

    _sostituzione_in_conflitto qui sopra guarda solo chi VIENE sostituito.
    Chi sostituisce non lo controllava nessuno, quindi la stessa persona
    poteva risultare contemporaneamente in due sedi, o essere mandata a
    coprire un giorno in cui è in ferie. Non è un errore che dia errore: la
    sostituzione veniva accettata, e il buco si scopriva quando al presidio
    non si presentava nessuno.

    Controlla solo le impossibilità vere — essere in due posti insieme,
    essere assente — e non se il sostituto ha un turno proprio quel giorno:
    spostare qualcuno dal suo turno per coprire altrove è una cosa che si fa
    di proposito, e bloccarla darebbe fastidio senza motivo.
    """
    gia_impegnato = (
        db.query(Sostituzione)
        .filter(
            Sostituzione.dipendente_sostituto_id == dipendente_sostituto_id,
            Sostituzione.data == data_sost,
        )
        .all()
    )
    for esistente in gia_impegnato:
        if inizio is None or esistente.ora_inizio is None:
            return (
                "Il sostituto scelto sta già sostituendo un altro dipendente in "
                "questa data: non può coprire due sedi contemporaneamente."
            )
        if esistente.ora_inizio < fine and esistente.ora_fine > inizio:
            return (
                "Il sostituto scelto sta già sostituendo un altro dipendente in "
                "questa data, in un orario che si sovrappone a quello indicato."
            )

    if _si_sovrappone(db, dipendente_sostituto_id, data_sost, data_sost):
        return (
            "Il sostituto scelto risulta assente (ferie, permesso o malattia) "
            "in questa data."
        )

    return None


@router.get("/sostituzioni")
def elenco_sostituzioni(
    request: Request,
    dipendente_id: int | None = None,
    data_da: str | None = None,
    data_a: str | None = None,
    precompila_partente_id: int | None = None,
    precompila_sede_id: int | None = None,
    precompila_data: str | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    """I tre parametri precompila_* arrivano dal pulsante "Organizza
    sostituzione" della pagina Copertura, sulla riga di chi risulta assente.

    Da lì si sa già chi manca, in quale palazzo e in che giorno: sono
    esattamente i campi obbligatori del form, che altrimenti vanno
    riselezionati a memoria dopo aver cambiato pagina — con 76 nomi in
    tendina, è il punto dove è facile scegliere la persona sbagliata. Il
    sostituto resta da scegliere, perché quella è l'unica vera decisione.

    Sono solo valori preselezionati nel form, non un'operazione: restano
    tutti modificabili, e la sostituzione nasce comunque solo dal POST, con
    i suoi controlli.
    """
    query = db.query(Sostituzione)
    if dipendente_id:
        query = query.filter(
            (Sostituzione.dipendente_partente_id == dipendente_id)
            | (Sostituzione.dipendente_sostituto_id == dipendente_id)
        )
    if data_da:
        query = query.filter(Sostituzione.data >= _data_o_400(data_da))
    if data_a:
        query = query.filter(Sostituzione.data <= _data_o_400(data_a))
    sostituzioni = query.order_by(Sostituzione.data.desc()).all()

    dipendenti = db.query(Dipendente).order_by(Dipendente.cognome, Dipendente.nome).all()
    sedi = db.query(Sede).filter(Sede.attivo == True).order_by(Sede.nome).all()  # noqa: E712

    return templates.TemplateResponse(
        request,
        "sostituzioni.html",
        {
            "sostituzioni": sostituzioni,
            "dipendenti": dipendenti,
            "sedi": sedi,
            "utente": utente,
            "filtri": {
                "dipendente_id": dipendente_id,
                "data_da": data_da or "",
                "data_a": data_a or "",
            },
            "precompila": {
                "partente_id": precompila_partente_id,
                "sede_id": precompila_sede_id,
                # Validata qui e non nel template: se arrivasse una data
                # malformata dall'indirizzo, un campo date la scarterebbe in
                # silenzio lasciando l'utente a chiedersi perché è vuoto.
                "data": _data_o_400(precompila_data).isoformat() if precompila_data else "",
            },
        },
    )


@router.post("/sostituzioni/nuova")
def crea_sostituzione(
    request: Request,
    dipendente_partente_id: int = Form(...),
    sede_partenza_id: int = Form(...),
    dipendente_sostituto_id: int = Form(...),
    sede_arrivo_id: int = Form(...),
    data: str = Form(...),
    ora_inizio: str = Form(""),
    ora_fine: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    if dipendente_partente_id == dipendente_sostituto_id:
        raise HTTPException(status_code=400, detail="Il dipendente non può sostituire se stesso.")

    dipendente_partente = ottieni_o_404(db, Dipendente, dipendente_partente_id)
    dipendente_sostituto = ottieni_o_404(db, Dipendente, dipendente_sostituto_id)
    sede_partenza = ottieni_o_404(db, Sede, sede_partenza_id)
    sede_arrivo = ottieni_o_404(db, Sede, sede_arrivo_id)

    data_sost = _data_o_400(data)
    inizio = _ora_opzionale_o_400(ora_inizio)
    fine = _ora_opzionale_o_400(ora_fine)
    if (inizio is None) != (fine is None):
        raise HTTPException(
            status_code=400,
            detail="Indica sia l'ora di inizio sia l'ora di fine, oppure lasciale entrambe vuote per l'intera giornata.",
        )
    if inizio is not None and fine <= inizio:
        raise HTTPException(status_code=400, detail="L'ora fine deve essere successiva all'ora inizio.")

    if _sostituzione_in_conflitto(db, dipendente_partente_id, data_sost, inizio, fine):
        raise HTTPException(
            status_code=400,
            detail="Esiste già una sostituzione per questo dipendente in questa data che si sovrappone all'orario indicato.",
        )

    motivo = _sostituto_non_disponibile(db, dipendente_sostituto_id, data_sost, inizio, fine)
    if motivo:
        raise HTTPException(status_code=400, detail=motivo)

    sostituzione = Sostituzione(
        data=data_sost,
        dipendente_partente_id=dipendente_partente_id,
        sede_partenza_id=sede_partenza_id,
        dipendente_sostituto_id=dipendente_sostituto_id,
        sede_arrivo_id=sede_arrivo_id,
        ora_inizio=inizio,
        ora_fine=fine,
        note=note.strip() or None,
        creato_da=utente.id,
    )
    db.add(sostituzione)
    db.flush()
    registra_modifica(
        db, utente.id, "sostituzioni", sostituzione.id, "creazione",
        f"dipendente_partente_id={dipendente_partente_id}, dipendente_sostituto_id={dipendente_sostituto_id}, "
        f"data={data_sost.isoformat()}, ora_inizio={ora_inizio or 'intera giornata'}, ora_fine={ora_fine or ''}",
    )
    db.commit()

    orario = f"{ora_inizio}-{ora_fine}" if inizio is not None else "intera giornata"
    invia_notifica_asincrona(
        f"Sostituzione registrata: {dipendente_partente.cognome} {dipendente_partente.nome}",
        "email_sostituzione.html",
        {
            "data": data_sost.isoformat(),
            "dipendente_partente_nome": f"{dipendente_partente.cognome} {dipendente_partente.nome}",
            "sede_partenza_nome": sede_partenza.nome,
            "dipendente_sostituto_nome": f"{dipendente_sostituto.cognome} {dipendente_sostituto.nome}",
            "sede_arrivo_nome": sede_arrivo.nome,
            "orario": orario,
            "note": sostituzione.note,
            "registrato_da": utente.username,
        },
    )
    imposta_flash(
        request,
        f"Sostituzione registrata: {dipendente_sostituto.cognome} {dipendente_sostituto.nome} "
        f"sostituisce {dipendente_partente.cognome} {dipendente_partente.nome} "
        f"il {data_sost.strftime('%d/%m/%Y')} ({orario}).",
        tipo="ok",
    )
    return RedirectResponse("/sostituzioni", status_code=303)


@router.post("/sostituzioni/{sostituzione_id}/elimina")
def elimina_sostituzione(
    request: Request,
    sostituzione_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    sostituzione = ottieni_o_404(db, Sostituzione, sostituzione_id)
    dettaglio = (
        f"dipendente_partente_id={sostituzione.dipendente_partente_id}, "
        f"dipendente_sostituto_id={sostituzione.dipendente_sostituto_id}, data={sostituzione.data.isoformat()}"
    )
    db.delete(sostituzione)
    registra_modifica(db, utente.id, "sostituzioni", sostituzione_id, "cancellazione", dettaglio)
    db.commit()
    imposta_flash(request, "Sostituzione eliminata.", tipo="ok")
    return RedirectResponse("/sostituzioni", status_code=303)

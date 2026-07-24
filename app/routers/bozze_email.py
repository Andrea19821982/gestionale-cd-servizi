"""Revisione delle bozze lette automaticamente dalle email di assenza/
sostituzione (vedi app/email_ingest.py e docs/06-formato-email-dipendenti.md).

Confermare una bozza segue esattamente le stesse regole di
app/routers/assenze.py e app/routers/sostituzioni.py (stesso controllo di
sovrapposizione, stessa copertura del calendario): confermare una bozza deve
avere l'identico effetto di un amministrativo che digita la stessa cosa a
mano, non un percorso parallelo con regole diverse."""

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app import impostazioni_email
from app.auth import RUOLI_SCRITTURA_ANAGRAFICA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.email_ingest import controlla_posta
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import Assenza, BozzaEmail, Dipendente, Sostituzione, Utente
from app.routers.assenze import _copri_giorni_con_assenza, _si_sovrappone
from app.routers.sostituzioni import _esiste_gia_sostituzione_giorno_intero
from app.templates import templates
from app.utils import fk_opzionale_o_400, ottieni_o_404

router = APIRouter()


def genera_testo_email_dipendenti(indirizzo: str) -> str:
    """Bozza pronta da copiare e inoltrare ai dipendenti (docs/06-formato-
    email-dipendenti.md in forma di email vera e propria, con saluto e
    esempi): spiega come scrivere per segnalare ferie/permessi/malattie e
    sostituzioni in un formato che app/email_ingest.py sa leggere da solo."""
    indirizzo_mostrato = indirizzo or "[inserisci qui l'indirizzo email dedicato]"
    return f"""Oggetto: Come segnalare ferie, permessi, malattie e sostituzioni

Ciao a tutti,

da oggi ferie, permessi, malattie e sostituzioni si possono segnalare anche scrivendo un'email a {indirizzo_mostrato}: il programma la legge in automatico e prepara subito la richiesta, che un amministrativo controlla e conferma prima che diventi effettiva.

Importante: finché non arriva la conferma, la richiesta non è ancora effettiva sul calendario. Se è urgente, avvisate comunque anche telefonicamente.

===================================
COME SEGNALARE UN'ASSENZA (ferie, malattia, permesso)
===================================

Oggetto dell'email: ASSENZA

Corpo dell'email, una riga per ogni campo, esattamente in questo formato:

Nome: Cognome Nome
Tipo: Ferie
Dal: gg/mm/aaaa
Al: gg/mm/aaaa
Note:

Esempio:

Nome: Mario Rossi
Tipo: Ferie
Dal: 10/08/2026
Al: 14/08/2026
Note: rientro il 15

===================================
COME SEGNALARE UNA SOSTITUZIONE
===================================

Oggetto dell'email: SOSTITUZIONE

Corpo dell'email:

Data: gg/mm/aaaa
Assente: Cognome Nome
Sostituto: Cognome Nome
Orario: intera giornata (oppure l'orario esatto, es. 09:00-13:00)

Esempio:

Data: 10/08/2026
Assente: Mario Rossi
Sostituto: Luca Verdi
Orario: intera giornata

===================================
REGOLE DA RISPETTARE
===================================

- Un'email = una sola assenza o una sola sostituzione. Per segnalarne più di una, mandate email separate.
- Scrivete sempre cognome e nome per intero (non solo il nome di battesimo), altrimenti il programma non riesce a capire di chi si tratta.
- Rispettate il formato "Etichetta: valore", una riga per campo.
- Se qualcosa non è chiaro (data scritta diversamente, nome non trovato), il programma non inventa nulla: segnala la richiesta come "da controllare" e la lascia a chi la deve confermare.

Grazie della collaborazione!
"""


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


@router.get("/bozze-email")
def elenco_bozze_email(
    request: Request,
    stato: str = "da_confermare",
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    query = db.query(BozzaEmail).options(
        joinedload(BozzaEmail.dipendente), joinedload(BozzaEmail.dipendente_sostituto)
    )
    if stato:
        query = query.filter(BozzaEmail.stato == stato)
    bozze = query.order_by(BozzaEmail.ricevuta_il.desc()).all()
    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )

    cfg = impostazioni_email.imap_effettivo(db)
    return templates.TemplateResponse(
        request,
        "bozze_email.html",
        {
            "bozze": bozze,
            "dipendenti": dipendenti,
            "stato_filtro": stato,
            "utente": utente,
            "indirizzo_email": cfg.utente,
            "testo_email_dipendenti": genera_testo_email_dipendenti(cfg.utente),
            "imap_host": cfg.host,
            "imap_porta": cfg.porta,
            "imap_utente": cfg.utente,
            "imap_cartella": cfg.cartella,
            "imap_password_impostata": bool(cfg.password),
        },
    )


@router.post("/bozze-email/controlla-ora")
def controlla_posta_ora(
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    controlla_posta()
    return RedirectResponse("/bozze-email", status_code=303)


@router.get("/bozze-email/guida-stampa")
def guida_email_stampa(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    """Vista pensata per la stampa/esportazione PDF dal browser (Ctrl+P /
    'Salva come PDF'), stesso schema di /calendario/stampa: contiene la
    bozza dell'email che i dipendenti devono mandare e la guida su come
    farlo, pronta da stampare o allegare in PDF a una comunicazione interna."""
    cfg = impostazioni_email.imap_effettivo(db)
    return templates.TemplateResponse(
        request,
        "guida_email_stampa.html",
        {"testo_email_dipendenti": genera_testo_email_dipendenti(cfg.utente)},
    )


@router.post("/bozze-email/imposta-imap")
def imposta_imap(
    request: Request,
    host: str = Form(""),
    porta: int = Form(993),
    imap_utente: str = Form(""),
    password: str = Form(""),
    cartella: str = Form("INBOX"),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Solo amministratore: qui sta l'indirizzo/password della casella
    email da cui si leggono le richieste dei dipendenti, informazione più
    sensibile della semplice gestione operativa del calendario."""
    impostazioni_email.salva_impostazioni(db, utente.id, host, porta, imap_utente, password, cartella)
    registra_modifica(
        db, utente.id, "impostazioni_imap", 1, "modifica",
        f"host={host.strip()}, utente={imap_utente.strip()}, cartella={cartella.strip()}",
    )
    imposta_flash(request, "Configurazione della casella email aggiornata.", tipo="ok")
    return RedirectResponse("/bozze-email", status_code=303)


@router.post("/bozze-email/{bozza_id}/conferma")
def conferma_bozza_email(
    bozza_id: int,
    dipendente_id: int = Form(...),
    dipendente_sostituto_id: str = Form(""),
    tipo_assenza: str = Form(""),
    data_inizio: str = Form(...),
    data_fine: str = Form(""),
    ora_inizio: str = Form(""),
    ora_fine: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Crea la vera Assenza o Sostituzione a partire dai campi del form
    (precompilati con quanto interpretato dall'email, ma sempre correggibili
    prima di confermare): la bozza da sola non crea mai nulla sul calendario."""
    bozza = ottieni_o_404(db, BozzaEmail, bozza_id)
    if bozza.stato != "da_confermare":
        raise HTTPException(status_code=400, detail="Questa bozza è già stata gestita.")

    dipendente = ottieni_o_404(db, Dipendente, dipendente_id)
    inizio = _data_o_400(data_inizio)

    if bozza.tipo == "assenza":
        fine = _data_o_400(data_fine) if data_fine else inizio
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
        _copri_giorni_con_assenza(db, dipendente, inizio, fine)
        registra_modifica(
            db, utente.id, "assenze", assenza.id, "creazione",
            f"da email (bozza {bozza.id}): dipendente_id={dipendente_id}, "
            f"{inizio.isoformat()}..{fine.isoformat()}, tipo={tipo_assenza}",
        )
        bozza.record_creato_tabella = "assenze"
        bozza.record_creato_id = assenza.id

    else:  # sostituzione
        sostituto_id = fk_opzionale_o_400(db, Dipendente, dipendente_sostituto_id)
        if sostituto_id is None:
            raise HTTPException(status_code=400, detail="Indica il dipendente sostituto.")
        if sostituto_id == dipendente_id:
            raise HTTPException(status_code=400, detail="Il dipendente non può sostituire se stesso.")
        if dipendente.sede_riferimento_id is None:
            raise HTTPException(
                status_code=400,
                detail="Il dipendente assente non ha una sede di riferimento: assegnala prima in Dipendenti.",
            )

        inizio_ora = _ora_opzionale_o_400(ora_inizio)
        fine_ora = _ora_opzionale_o_400(ora_fine)
        if (inizio_ora is None) != (fine_ora is None):
            raise HTTPException(
                status_code=400,
                detail="Indica sia l'ora di inizio sia l'ora di fine, oppure lasciale entrambe vuote per l'intera giornata.",
            )
        if inizio_ora is not None and fine_ora <= inizio_ora:
            raise HTTPException(status_code=400, detail="L'ora fine deve essere successiva all'ora inizio.")
        if inizio_ora is None and _esiste_gia_sostituzione_giorno_intero(db, dipendente_id, inizio):
            raise HTTPException(
                status_code=400,
                detail="Esiste già una sostituzione per l'intera giornata per questo dipendente in questa data.",
            )

        sostituzione = Sostituzione(
            data=inizio,
            dipendente_partente_id=dipendente_id,
            sede_partenza_id=dipendente.sede_riferimento_id,
            dipendente_sostituto_id=sostituto_id,
            sede_arrivo_id=dipendente.sede_riferimento_id,
            ora_inizio=inizio_ora,
            ora_fine=fine_ora,
            note=note.strip() or None,
            creato_da=utente.id,
        )
        db.add(sostituzione)
        db.flush()
        registra_modifica(
            db, utente.id, "sostituzioni", sostituzione.id, "creazione",
            f"da email (bozza {bozza.id}): dipendente_partente_id={dipendente_id}, "
            f"dipendente_sostituto_id={sostituto_id}, data={inizio.isoformat()}",
        )
        bozza.record_creato_tabella = "sostituzioni"
        bozza.record_creato_id = sostituzione.id

    bozza.stato = "confermata"
    bozza.confermata_da = utente.id
    bozza.confermata_il = datetime.now()
    registra_modifica(db, utente.id, "bozze_email", bozza.id, "modifica", "stato=confermata")
    db.commit()
    return RedirectResponse("/bozze-email", status_code=303)


@router.post("/bozze-email/{bozza_id}/scarta")
def scarta_bozza_email(
    bozza_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    bozza = ottieni_o_404(db, BozzaEmail, bozza_id)
    if bozza.stato != "da_confermare":
        raise HTTPException(status_code=400, detail="Questa bozza è già stata gestita.")
    bozza.stato = "scartata"
    bozza.confermata_da = utente.id
    bozza.confermata_il = datetime.now()
    registra_modifica(db, utente.id, "bozze_email", bozza.id, "modifica", "stato=scartata")
    db.commit()
    return RedirectResponse("/bozze-email", status_code=303)

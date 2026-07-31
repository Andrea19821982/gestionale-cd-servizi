"""Revisione delle bozze lette automaticamente dalle email di assenza/
sostituzione (vedi app/email_ingest.py e docs/06-formato-email-dipendenti.md).

Confermare una bozza segue esattamente le stesse regole di
app/routers/assenze.py e app/routers/sostituzioni.py (stesso controllo di
sovrapposizione, stessa copertura del calendario): confermare una bozza deve
avere l'identico effetto di un amministrativo che digita la stessa cosa a
mano, non un percorso parallelo con regole diverse."""

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app import email_config, email_service, impostazioni_email
from app.auth import RUOLI_SCRITTURA_ANAGRAFICA, RUOLI_SCRITTURA_OPERATIVO, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.email_ingest import controlla_posta
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import Assenza, BozzaEmail, Dipendente, Sostituzione, Utente
from app.paths import cartella_risorse
from app.routers.assenze import _copri_giorni_con_assenza, _malattia, _si_sovrappone
from app.routers.sostituzioni import _sostituto_non_disponibile, _sostituzione_in_conflitto
from app.templates import templates
from app.utils import fk_opzionale_o_400, ottieni_o_404

router = APIRouter()

# I due moduli ufficiali (Word) preparati per i dipendenti: scaricabili da
# /bozze-email e allegabili all'invio diretto (vedi invia_procedura sotto).
# Sostituiscono, come contenuto mostrato in evidenza sulla pagina, i vecchi
# moduli generati automaticamente in PDF (genera_modulo_assenza/sostituzione
# più sotto restano comunque disponibili come funzioni/route per compatibilità
# con chi ci fosse già arrivato con un link diretto).
_NOME_FILE_PROCEDURA_ASSENZE = "Procedura_Segnalazione_Assenze_CD-Servizi.docx"
_NOME_FILE_PROCEDURA_SOSTITUZIONI = "Procedura_Segnalazione_Sostituzioni_CD-Servizi.docx"
_TIPO_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _percorso_procedura(nome_file: str):
    return cartella_risorse() / "static" / "documenti" / nome_file


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


def esempio_corpo_assenza() -> str:
    """Corpo dell'esempio già compilato mostrato nel modulo assenze (vedi
    genera_modulo_assenza sotto): un'unica fonte, così l'esempio stampato
    nel PDF è esattamente lo stesso testo verificato da
    tests/test_impostazioni_email.py e tests/test_email_ingest.py contro
    app/email_ingest.py — se cambia qui, cambia anche cosa viene testato,
    non può disallinearsi in silenzio."""
    return (
        "Nome: Mario Rossi\n"
        "Tipo: Ferie\n"
        "Dal: 10/08/2026\n"
        "Al: 14/08/2026\n"
        "Note: rientro il 15\n"
    )


def esempio_corpo_sostituzione() -> str:
    """Vedi esempio_corpo_assenza sopra: stessa logica, per il modulo
    sostituzioni."""
    return (
        "Data: 10/08/2026\n"
        "Assente: Mario Rossi\n"
        "Sostituto: Luca Verdi\n"
        "Orario: intera giornata\n"
    )


def genera_modulo_assenza(indirizzo: str) -> str:
    """Modulo autonomo pronto da inoltrare via email, pensato per essere
    stampato/salvato in PDF (vedi /bozze-email/modulo-assenza-stampa) e
    inoltrato da solo ai dipendenti che devono segnalare un'assenza: a
    differenza di genera_testo_email_dipendenti() sopra (guida completa con
    entrambi gli argomenti), questo copre solo le assenze."""
    indirizzo_mostrato = indirizzo or "[inserisci qui l'indirizzo email dedicato]"
    return f"""MODULO PER SEGNALARE UN'ASSENZA (ferie, malattia, permesso)

Copia il modulo qui sotto nel corpo di una nuova email, compila i campi con
i tuoi dati e invialo a: {indirizzo_mostrato}
Oggetto dell'email (scrivilo esattamente così nel campo oggetto): ASSENZA

===================================
MODULO DA COMPILARE
===================================

Nome:
Tipo:
Dal: gg/mm/aaaa
Al: gg/mm/aaaa
Note:

===================================
ISTRUZIONI PER COMPILARE CORRETTAMENTE
===================================

- Nome: cognome e nome per intero (es. "Rossi Mario"), non solo il nome di battesimo: il programma deve trovare esattamente il tuo nominativo tra i dipendenti attivi.
- Tipo: il motivo dell'assenza, per esempio Ferie, Malattia oppure Permesso.
- Dal / Al: data di inizio e fine, nel formato giorno/mese/anno (es. 10/08/2026). Se l'assenza dura un solo giorno, scrivi la stessa data in entrambi i campi.
- Note: facoltativo, per aggiungere dettagli (es. "rientro il 15").
- Rispetta il formato "Etichetta: valore", una riga per campo, esattamente come nel modulo sopra: il programma legge da solo l'email e prepara la richiesta, che un amministrativo controlla e conferma prima che diventi effettiva sul calendario.
- Un'email = una sola assenza. Per segnalarne più di una, manda email separate.
- Se qualcosa non è chiaro (data scritta diversamente, nome non trovato), il programma non inventa nulla: segnala la richiesta come "da controllare" e la lascia a chi la deve confermare. Se è urgente, avvisa comunque anche telefonicamente.

===================================
ESEMPIO GIÀ COMPILATO
===================================

Oggetto: ASSENZA

{esempio_corpo_assenza()}"""


def genera_modulo_sostituzione(indirizzo: str) -> str:
    """Vedi genera_modulo_assenza sopra: stesso schema, ma per le
    sostituzioni (vedi /bozze-email/modulo-sostituzione-stampa)."""
    indirizzo_mostrato = indirizzo or "[inserisci qui l'indirizzo email dedicato]"
    return f"""MODULO PER SEGNALARE UNA SOSTITUZIONE

Copia il modulo qui sotto nel corpo di una nuova email, compila i campi e
invialo a: {indirizzo_mostrato}
Oggetto dell'email (scrivilo esattamente così nel campo oggetto): SOSTITUZIONE

===================================
MODULO DA COMPILARE
===================================

Data: gg/mm/aaaa
Assente:
Sostituto:
Orario:

===================================
ISTRUZIONI PER COMPILARE CORRETTAMENTE
===================================

- Data: il giorno della sostituzione, nel formato giorno/mese/anno (es. 10/08/2026).
- Assente: cognome e nome per intero del dipendente che va sostituito (es. "Rossi Mario").
- Sostituto: cognome e nome per intero di chi lo sostituisce.
- Orario: scrivi "intera giornata" se la sostituzione copre tutto il turno, oppure l'orario esatto nel formato OO:MM-OO:MM (es. 09:00-13:00) se copre solo alcune ore.
- Scrivi sempre cognome e nome per intero (non solo il nome di battesimo) sia per l'assente sia per il sostituto: il programma deve trovare esattamente i due nominativi tra i dipendenti attivi, senza poter confondere l'uno con l'altro.
- Rispetta il formato "Etichetta: valore", una riga per campo, esattamente come nel modulo sopra.
- Un'email = una sola sostituzione. Per segnalarne più di una, manda email separate.
- Se qualcosa non è chiaro, il programma non inventa nulla: segnala la richiesta come "da controllare" e la lascia a chi la deve confermare.

===================================
ESEMPIO GIÀ COMPILATO
===================================

Oggetto: SOSTITUZIONE

{esempio_corpo_sostituzione()}"""


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

    dipendenti_con_email = [d for d in dipendenti if d.email]

    cfg = impostazioni_email.imap_effettivo(db)
    imap_host, imap_porta, imap_utente, imap_cartella, imap_password_impostata = impostazioni_email.campi_grezzi(db)
    return templates.TemplateResponse(
        request,
        "bozze_email.html",
        {
            "bozze": bozze,
            "dipendenti": dipendenti,
            "dipendenti_con_email": dipendenti_con_email,
            "dipendenti_senza_email_count": len(dipendenti) - len(dipendenti_con_email),
            "smtp_configurato": email_config.smtp_configurato(),
            "stato_filtro": stato,
            "utente": utente,
            "indirizzo_email": cfg.utente,
            "testo_email_dipendenti": genera_testo_email_dipendenti(cfg.utente),
            # Valori grezzi (quello che è davvero salvato in DB), non
            # imap_effettivo(): il form di modifica va precompilato con
            # ciò che l'amministratore ha davvero scritto, non con un
            # eventuale ripiego sul file, altrimenti un campo nuovo
            # salvato ma non "completo" (manca ancora la password)
            # sembra scomparire al ricaricamento — vedi campi_grezzi.
            "imap_host": imap_host,
            "imap_porta": imap_porta,
            "imap_utente": imap_utente,
            "imap_cartella": imap_cartella,
            "imap_password_impostata": imap_password_impostata,
        },
    )


@router.get("/bozze-email/procedura-assenze")
def scarica_procedura_assenze(
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    return FileResponse(
        _percorso_procedura(_NOME_FILE_PROCEDURA_ASSENZE),
        media_type=_TIPO_MIME_DOCX,
        filename=_NOME_FILE_PROCEDURA_ASSENZE,
    )


@router.get("/bozze-email/procedura-sostituzioni")
def scarica_procedura_sostituzioni(
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    return FileResponse(
        _percorso_procedura(_NOME_FILE_PROCEDURA_SOSTITUZIONI),
        media_type=_TIPO_MIME_DOCX,
        filename=_NOME_FILE_PROCEDURA_SOSTITUZIONI,
    )


@router.post("/bozze-email/invia-procedura")
def invia_procedura(
    request: Request,
    tipo: str = Form(...),
    dipendente_id: list[int] = Form([]),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Invia il modulo Word (assenze o sostituzioni) per email a ciascun
    dipendente selezionato, uno per uno (mai in copia agli altri: gli
    indirizzi dei colleghi non sono affari loro). Sincrono: chi preme
    "Invia" aspetta il risultato e vede subito quanti invii sono andati a
    buon fine, invece di scoprirlo dopo da un log."""
    if tipo not in ("assenza", "sostituzione"):
        raise HTTPException(status_code=400, detail="Tipo di procedura non valido.")
    if not email_config.smtp_configurato():
        imposta_flash(
            request,
            "Il server SMTP per l'invio non è configurato (vedi app/email_config.py sul server).",
            tipo="errore",
        )
        return RedirectResponse("/bozze-email", status_code=303)

    if tipo == "assenza":
        nome_file = _NOME_FILE_PROCEDURA_ASSENZE
        oggetto = "Procedura per segnalare assenze (ferie, malattia, permessi)"
        corpo = (
            "Ciao,\n\nin allegato trovi il modulo con le istruzioni per segnalare via email "
            "ferie, malattie e permessi. Segui il formato indicato: il programma legge la tua "
            "email in automatico e prepara la richiesta, che un amministrativo controlla e "
            "conferma prima che diventi effettiva sul calendario.\n\nGrazie della collaborazione!"
        )
    else:
        nome_file = _NOME_FILE_PROCEDURA_SOSTITUZIONI
        oggetto = "Procedura per segnalare sostituzioni"
        corpo = (
            "Ciao,\n\nin allegato trovi il modulo con le istruzioni per segnalare via email una "
            "sostituzione. Segui il formato indicato: il programma legge la tua email in "
            "automatico e prepara la richiesta, che un amministrativo controlla e conferma prima "
            "che diventi effettiva sul calendario.\n\nGrazie della collaborazione!"
        )

    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.id.in_(dipendente_id), Dipendente.email.isnot(None))
        .all()
        if dipendente_id else []
    )
    if not dipendenti:
        imposta_flash(request, "Nessun dipendente selezionato (con email impostata).", tipo="errore")
        return RedirectResponse("/bozze-email", status_code=303)

    percorso_allegato = _percorso_procedura(nome_file)
    falliti = []
    for dipendente in dipendenti:
        errore = email_service.invia_email_con_allegato(oggetto, corpo, dipendente.email, percorso_allegato)
        if errore:
            falliti.append(f"{dipendente.cognome} {dipendente.nome} ({errore})")

    riusciti = len(dipendenti) - len(falliti)

    if falliti:
        imposta_flash(
            request,
            f"Inviato a {riusciti} di {len(dipendenti)} dipendenti. Falliti: {'; '.join(falliti)}",
            tipo="avviso" if riusciti else "errore",
        )
    else:
        imposta_flash(request, f"Modulo inviato a {riusciti} dipendenti.", tipo="ok")
    return RedirectResponse("/bozze-email", status_code=303)


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


@router.get("/bozze-email/modulo-assenza-stampa")
def modulo_assenza_stampa(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    """PDF autonomo (solo assenze) pronto da inoltrare da solo ai
    dipendenti, separato dalla guida completa sopra: vedi
    genera_modulo_assenza()."""
    cfg = impostazioni_email.imap_effettivo(db)
    return templates.TemplateResponse(
        request,
        "modulo_email_stampa.html",
        {
            "titolo_pagina": "Modulo assenze — Gestionale CD Servizi",
            "testo_modulo": genera_modulo_assenza(cfg.utente),
        },
    )


@router.get("/bozze-email/modulo-sostituzione-stampa")
def modulo_sostituzione_stampa(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_OPERATIVO)),
):
    """PDF autonomo (solo sostituzioni), vedi modulo_assenza_stampa sopra."""
    cfg = impostazioni_email.imap_effettivo(db)
    return templates.TemplateResponse(
        request,
        "modulo_email_stampa.html",
        {
            "titolo_pagina": "Modulo sostituzioni — Gestionale CD Servizi",
            "testo_modulo": genera_modulo_sostituzione(cfg.utente),
        },
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
    db.commit()  # impostazione e riga di log insieme, o nessuna delle due
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

        approvazione_automatica = _malattia(tipo_assenza)
        assenza = Assenza(
            dipendente_id=dipendente_id,
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
            f"da email (bozza {bozza.id}): dipendente_id={dipendente_id}, "
            f"{inizio.isoformat()}..{fine.isoformat()}, tipo={tipo_assenza}, "
            f"stato={'approvata' if approvazione_automatica else 'richiesta'}",
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
        if _sostituzione_in_conflitto(db, dipendente_id, inizio, inizio_ora, fine_ora):
            raise HTTPException(
                status_code=400,
                detail="Esiste già una sostituzione per questo dipendente in questa data che si sovrappone all'orario indicato.",
            )
        # Stesso controllo del form manuale: una bozza arrivata per email non
        # è più affidabile di quanto scrive a mano l'amministrativo, e qui il
        # sostituto lo propone chi ha scritto l'email.
        motivo = _sostituto_non_disponibile(db, sostituto_id, inizio, inizio_ora, fine_ora)
        if motivo:
            raise HTTPException(status_code=400, detail=motivo)

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

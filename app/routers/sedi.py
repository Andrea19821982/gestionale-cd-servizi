from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_LETTURA, RUOLI_SCRITTURA_ANAGRAFICA, richiedi_ruolo
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.flash import imposta_flash
from app.logging_service import registra_modifica
from app.models import Dipendente, Sede, SottosezioneCopertura, Utente
from app.templates import templates
from app.utils import chiave_sottosezione, checkbox_a_bool, ottieni_o_404

router = APIRouter()


def _intero_non_negativo_o_400(valore: str) -> int:
    numero = _intero_o_400(valore)
    if numero < 0:
        raise HTTPException(status_code=400, detail="Il valore non può essere negativo.")
    return numero


def _intero_o_400(valore: str) -> int:
    try:
        return int(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Valore non valido: {valore!r}")


@router.get("/sedi")
def elenco_sedi(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    sedi = db.query(Sede).order_by(Sede.ordine_visualizzazione, Sede.nome).all()
    comparti = (
        db.query(SottosezioneCopertura)
        .options(joinedload(SottosezioneCopertura.sede))
        .join(Sede)
        .order_by(Sede.nome, SottosezioneCopertura.nome)
        .all()
    )
    # Serve a mostrare, dentro il form del comparto, chi di quel palazzo
    # farne parte: assegnare le persone da qui evita di doverle aprire una
    # per una in Dipendenti dopo aver creato il comparto.
    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )
    membri_per_comparto = {
        c.id: {
            d.id for d in dipendenti
            if d.sede_riferimento_id == c.sede_id
            and d.sottosezione
            and chiave_sottosezione(d.sottosezione) == chiave_sottosezione(c.nome)
        }
        for c in comparti
    }
    return templates.TemplateResponse(
        request,
        "sedi.html",
        {
            "sedi": sedi,
            "comparti": comparti,
            "dipendenti": dipendenti,
            "membri_per_comparto": membri_per_comparto,
            "utente": utente,
        },
    )


@router.post("/sedi/nuova")
def crea_sede(
    request: Request,
    nome: str = Form(...),
    colore_hex: str = Form(...),
    copertura_minima_mattina: str = Form("0"),
    copertura_minima_pomeriggio: str = Form("0"),
    ordine_visualizzazione: str = Form("0"),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    sede = Sede(
        nome=nome.strip(),
        colore_hex=colore_hex.strip(),
        attivo=True,
        copertura_minima_mattina=_intero_non_negativo_o_400(copertura_minima_mattina),
        copertura_minima_pomeriggio=_intero_non_negativo_o_400(copertura_minima_pomeriggio),
        ordine_visualizzazione=_intero_o_400(ordine_visualizzazione),
    )
    db.add(sede)
    db.flush()
    registra_modifica(db, utente.id, "sedi", sede.id, "creazione", f"nome={sede.nome}")
    db.commit()
    return RedirectResponse("/sedi", status_code=303)


@router.post("/sedi/{sede_id}/modifica")
def modifica_sede(
    request: Request,
    sede_id: int,
    nome: str = Form(...),
    colore_hex: str = Form(...),
    copertura_minima_mattina: str = Form("0"),
    copertura_minima_pomeriggio: str = Form("0"),
    ordine_visualizzazione: str = Form("0"),
    attivo: str = Form(None),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    sede = ottieni_o_404(db, Sede, sede_id)
    sede.nome = nome.strip()
    sede.colore_hex = colore_hex.strip()
    sede.copertura_minima_mattina = _intero_non_negativo_o_400(copertura_minima_mattina)
    sede.copertura_minima_pomeriggio = _intero_non_negativo_o_400(copertura_minima_pomeriggio)
    sede.ordine_visualizzazione = _intero_o_400(ordine_visualizzazione)
    sede.attivo = checkbox_a_bool(attivo)
    registra_modifica(
        db, utente.id, "sedi", sede.id, "modifica",
        f"nome={sede.nome}, colore_hex={sede.colore_hex}, "
        f"copertura_minima_mattina={sede.copertura_minima_mattina}, "
        f"copertura_minima_pomeriggio={sede.copertura_minima_pomeriggio}, "
        f"ordine_visualizzazione={sede.ordine_visualizzazione}, attivo={sede.attivo}",
    )
    db.commit()
    return RedirectResponse("/sedi", status_code=303)


def _rifiuta_comparto_duplicato(db: Session, sede_id: int, nome: str, escludi_id: int | None = None) -> None:
    """Il vincolo UNIQUE(sede_id, nome) nel DB è un confronto esatto,
    case-sensitive: da solo non impedisce "Parcheggio" e "parcheggio " nella
    stessa sede. calcola_copertura invece li abbina con chiave_sottosezione
    (normalizzata), quindi i due finirebbero a collassare sulla stessa
    chiave: uno dei due minimi sparirebbe silenziosamente dal cruscotto
    Copertura, senza nessun errore né avviso. Meglio bloccarlo qui."""
    chiave = chiave_sottosezione(nome)
    query = db.query(SottosezioneCopertura).filter(SottosezioneCopertura.sede_id == sede_id)
    if escludi_id is not None:
        query = query.filter(SottosezioneCopertura.id != escludi_id)
    for esistente in query.all():
        if chiave_sottosezione(esistente.nome) == chiave:
            raise HTTPException(
                status_code=400,
                detail=f"Esiste già un comparto \"{esistente.nome}\" in questa sede: differisce solo per "
                "maiuscole o spazi, che nel calcolo della copertura vengono ignorati e farebbero sparire "
                "silenziosamente uno dei due minimi configurati.",
            )


def _applica_membri(db: Session, comparto: SottosezioneCopertura, dipendente_ids: list[int], utente_id: int) -> int:
    """Allinea chi appartiene al comparto a quanto spuntato nel form:
    scrive il nome del comparto in Dipendente.sottosezione a chi è stato
    selezionato e lo toglie a chi è stato deselezionato. Tocca solo i
    dipendenti della stessa sede del comparto (gli altri non potrebbero
    comunque farne parte, vedi calcola_copertura) e solo chi già apparteneva
    a QUESTO comparto: chi sta in un altro comparto della stessa sede non
    deve essere svuotato per il fatto di non essere spuntato qui.

    Restituisce quanti dipendenti sono stati modificati."""
    selezionati = set(dipendente_ids)
    chiave = chiave_sottosezione(comparto.nome)
    modificati = 0
    for dipendente in db.query(Dipendente).filter(Dipendente.sede_riferimento_id == comparto.sede_id).all():
        era_membro = bool(dipendente.sottosezione) and chiave_sottosezione(dipendente.sottosezione) == chiave
        deve_essere_membro = dipendente.id in selezionati
        if era_membro == deve_essere_membro:
            continue
        if deve_essere_membro and dipendente.sottosezione and not era_membro:
            continue  # già in un altro comparto: non lo si sposta a sorpresa da qui
        dipendente.sottosezione = comparto.nome if deve_essere_membro else None
        registra_modifica(
            db, utente_id, "dipendenti", dipendente.id, "modifica",
            f"cognome={dipendente.cognome}, nome={dipendente.nome}, sottosezione={dipendente.sottosezione}",
        )
        modificati += 1
    return modificati


@router.post("/sedi/comparti/nuovo")
def crea_comparto_copertura(
    request: Request,
    sede_id: int = Form(...),
    nome: str = Form(...),
    copertura_minima_mattina: str = Form("0"),
    copertura_minima_pomeriggio: str = Form("0"),
    dipendente_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    ottieni_o_404(db, Sede, sede_id)
    _rifiuta_comparto_duplicato(db, sede_id, nome.strip())
    comparto = SottosezioneCopertura(
        sede_id=sede_id,
        nome=nome.strip(),
        copertura_minima_mattina=_intero_non_negativo_o_400(copertura_minima_mattina),
        copertura_minima_pomeriggio=_intero_non_negativo_o_400(copertura_minima_pomeriggio),
    )
    db.add(comparto)
    db.flush()
    registra_modifica(
        db, utente.id, "sottosezioni_copertura", comparto.id, "creazione",
        f"sede_id={sede_id}, nome={comparto.nome}",
    )
    assegnati = _applica_membri(db, comparto, dipendente_ids, utente.id)
    db.commit()
    imposta_flash(
        request,
        f"Comparto \"{comparto.nome}\" creato"
        + (f" con {assegnati} dipendent{'e' if assegnati == 1 else 'i'}." if assegnati else
           ". Nessun dipendente assegnato: puoi farlo da qui con Modifica."),
        tipo="ok",
    )
    return RedirectResponse("/sedi", status_code=303)


@router.post("/sedi/comparti/{comparto_id}/modifica")
def modifica_comparto_copertura(
    request: Request,
    comparto_id: int,
    sede_id: int = Form(...),
    nome: str = Form(...),
    copertura_minima_mattina: str = Form("0"),
    copertura_minima_pomeriggio: str = Form("0"),
    dipendente_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    comparto = ottieni_o_404(db, SottosezioneCopertura, comparto_id)
    ottieni_o_404(db, Sede, sede_id)
    _rifiuta_comparto_duplicato(db, sede_id, nome.strip(), escludi_id=comparto.id)
    nome_precedente = comparto.nome
    comparto.sede_id = sede_id
    comparto.nome = nome.strip()
    comparto.copertura_minima_mattina = _intero_non_negativo_o_400(copertura_minima_mattina)
    comparto.copertura_minima_pomeriggio = _intero_non_negativo_o_400(copertura_minima_pomeriggio)
    registra_modifica(
        db, utente.id, "sottosezioni_copertura", comparto.id, "modifica",
        f"sede_id={sede_id}, nome={comparto.nome}",
    )
    # Rinominare un comparto lascerebbe i suoi dipendenti col vecchio nome
    # scritto in Sottosezione, quindi scollegati dal minimo di copertura
    # (vedi calcola_copertura): vanno riallineati esplicitamente al nome
    # nuovo, e _applica_membri lo fa da sé perché confronta col nome nuovo.
    if chiave_sottosezione(nome_precedente) != chiave_sottosezione(comparto.nome):
        for dipendente in db.query(Dipendente).filter(Dipendente.sede_riferimento_id == comparto.sede_id).all():
            if dipendente.sottosezione and chiave_sottosezione(dipendente.sottosezione) == chiave_sottosezione(nome_precedente):
                dipendente.sottosezione = comparto.nome
    _applica_membri(db, comparto, dipendente_ids, utente.id)
    db.commit()
    imposta_flash(request, f"Comparto \"{comparto.nome}\" aggiornato.", tipo="ok")
    return RedirectResponse("/sedi", status_code=303)


@router.post("/sedi/comparti/{comparto_id}/elimina")
def elimina_comparto_copertura(
    request: Request,
    comparto_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Eliminare un comparto rimette i suoi dipendenti nel palazzo: si
    svuota il loro Dipendente.sottosezione, così spariscono come gruppo a
    sé e tornano nell'elenco normale della sede, sia nel calendario sia in
    Copertura (vedi _raggruppa_per_sottosezione e calcola_copertura).

    Senza questo passaggio il comparto sparirebbe solo dall'elenco qui: i
    dipendenti resterebbero raggruppati sotto un'intestazione che non
    corrisponde più a niente, con un minimo di copertura ricaduto a 0 in
    silenzio — cioè un gruppo che sembra monitorato e non lo è più.

    Vale anche per i disattivati: lasciar loro la sottosezione farebbe
    ricomparire il gruppo fantasma il giorno in cui vengono riattivati."""
    comparto = ottieni_o_404(db, SottosezioneCopertura, comparto_id)
    chiave = chiave_sottosezione(comparto.nome)
    dipendenti_collegati = [
        d for d in db.query(Dipendente).filter(
            Dipendente.sede_riferimento_id == comparto.sede_id
        ).all()
        if d.sottosezione and chiave_sottosezione(d.sottosezione) == chiave
    ]
    nome_comparto = comparto.nome
    nome_sede = comparto.sede.nome if comparto.sede else "la sede"

    for dipendente in dipendenti_collegati:
        dipendente.sottosezione = None
        registra_modifica(
            db, utente.id, "dipendenti", dipendente.id, "modifica",
            f"cognome={dipendente.cognome}, nome={dipendente.nome}, sottosezione=None "
            f"(comparto {nome_comparto} eliminato)",
        )
    registra_modifica(
        db, utente.id, "sottosezioni_copertura", comparto.id, "cancellazione",
        f"sede_id={comparto.sede_id}, nome={nome_comparto}, "
        f"dipendenti rimessi nel palazzo={len(dipendenti_collegati)}",
    )
    db.delete(comparto)
    db.commit()

    if dipendenti_collegati:
        quanti = len(dipendenti_collegati)
        imposta_flash(
            request,
            f"Comparto \"{nome_comparto}\" eliminato: {quanti} dipendent{'e' if quanti == 1 else 'i'} "
            f"{'è tornato' if quanti == 1 else 'sono tornati'} nell'elenco di {nome_sede}.",
            tipo="ok",
        )
    else:
        imposta_flash(request, f"Comparto \"{nome_comparto}\" eliminato.", tipo="ok")
    return RedirectResponse("/sedi", status_code=303)

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
    return templates.TemplateResponse(
        request, "sedi.html", {"sedi": sedi, "comparti": comparti, "utente": utente}
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


@router.post("/sedi/comparti/nuovo")
def crea_comparto_copertura(
    request: Request,
    sede_id: int = Form(...),
    nome: str = Form(...),
    copertura_minima_mattina: str = Form("0"),
    copertura_minima_pomeriggio: str = Form("0"),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    ottieni_o_404(db, Sede, sede_id)
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
    db.commit()
    return RedirectResponse("/sedi", status_code=303)


@router.post("/sedi/comparti/{comparto_id}/modifica")
def modifica_comparto_copertura(
    request: Request,
    comparto_id: int,
    sede_id: int = Form(...),
    nome: str = Form(...),
    copertura_minima_mattina: str = Form("0"),
    copertura_minima_pomeriggio: str = Form("0"),
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    comparto = ottieni_o_404(db, SottosezioneCopertura, comparto_id)
    ottieni_o_404(db, Sede, sede_id)
    comparto.sede_id = sede_id
    comparto.nome = nome.strip()
    comparto.copertura_minima_mattina = _intero_non_negativo_o_400(copertura_minima_mattina)
    comparto.copertura_minima_pomeriggio = _intero_non_negativo_o_400(copertura_minima_pomeriggio)
    registra_modifica(
        db, utente.id, "sottosezioni_copertura", comparto.id, "modifica",
        f"sede_id={sede_id}, nome={comparto.nome}",
    )
    db.commit()
    return RedirectResponse("/sedi", status_code=303)


@router.post("/sedi/comparti/{comparto_id}/elimina")
def elimina_comparto_copertura(
    request: Request,
    comparto_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    """Eliminare un comparto non tocca mai i dipendenti: Dipendente.sottosezione
    resta un campo libero (non una FK, vedi il modello), quindi qui non c'è
    nessun vincolo di integrità da rispettare. Ma se qualcuno ha ancora quel
    nome scritto in Sottosezione, dopo l'eliminazione il suo gruppo in
    Copertura resta visibile, semplicemente senza più un minimo configurato
    (ricade a 0, vedi calcola_copertura) — comportamento silenzioso che vale
    la pena segnalare subito a chi elimina, invece di lasciarlo scoprire
    dopo che l'allarme copertura ha smesso di scattare per quel gruppo."""
    comparto = ottieni_o_404(db, SottosezioneCopertura, comparto_id)
    chiave = chiave_sottosezione(comparto.nome)
    dipendenti_collegati = [
        d for d in db.query(Dipendente).filter(
            Dipendente.sede_riferimento_id == comparto.sede_id,
            Dipendente.attivo == True,  # noqa: E712
        ).all()
        if d.sottosezione and chiave_sottosezione(d.sottosezione) == chiave
    ]
    nome_comparto = comparto.nome
    registra_modifica(
        db, utente.id, "sottosezioni_copertura", comparto.id, "cancellazione",
        f"sede_id={comparto.sede_id}, nome={nome_comparto}",
    )
    db.delete(comparto)
    db.commit()

    if dipendenti_collegati:
        nomi = ", ".join(f"{d.cognome} {d.nome}" for d in dipendenti_collegati)
        imposta_flash(
            request,
            f"Comparto \"{nome_comparto}\" eliminato. {len(dipendenti_collegati)} dipendenti hanno ancora questa "
            f"sottosezione ({nomi}): restano un gruppo separato in Copertura ma senza più un minimo configurato, "
            f"finché non aggiorni il loro campo Sottosezione o non ricrei il comparto.",
            tipo="avviso",
        )
    else:
        imposta_flash(request, f"Comparto \"{nome_comparto}\" eliminato.", tipo="ok")
    return RedirectResponse("/sedi", status_code=303)

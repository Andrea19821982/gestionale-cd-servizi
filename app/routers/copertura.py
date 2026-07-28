"""Cruscotto "chi manca oggi in ogni sede": una vista rapida pensata per
capire subito dove serve una sostituzione, senza dover leggere il calendario
mensile cella per cella (backlog Zucchetti: cruscotto di copertura)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.auth import RUOLI_LETTURA, richiedi_ruolo
from app.database import get_db
from app.models import (
    AssegnazioneGiornaliera,
    Dipendente,
    EventoSala,
    Sala,
    Sede,
    SottosezioneCopertura,
    Sostituzione,
    Utente,
)
from app.templates import templates
from app.utils import chiave_sottosezione

router = APIRouter()


def _data_o_400(valore: str) -> date:
    try:
        return date.fromisoformat(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data non valida: {valore!r}")


def _righe_presenza(dipendenti: list[Dipendente], assegnazioni: dict[int, AssegnazioneGiornaliera]) -> list[dict]:
    righe = []
    for dip in dipendenti:
        assegnazione = assegnazioni.get(dip.id)
        if assegnazione is None:
            stato = "non_pianificato"
        elif assegnazione.origine == "assenza":
            stato = "assente"
        elif assegnazione.tipo_turno_id is not None:
            stato = "presente"
        else:
            stato = "non_pianificato"
        righe.append({"dipendente": dip, "stato": stato, "assegnazione": assegnazione})
    return righe


def _presenti_per_fascia(righe: list[dict]) -> dict[str, int]:
    """Quanti presenti in ciascuna fascia (mattina/pomeriggio), secondo
    TipoTurno.fascia del turno assegnato. Un turno "entrambe" (es. un
    intermedio 11:00-17:30, che copre parte di entrambe) fa contare la
    persona sia per il minimo mattina sia per quello pomeriggio: non è un
    caso raro da trascurare, è esattamente il tipo di turno che serve per un
    comparto coperto su un solo turno atipico invece che su due come il
    resto del palazzo.

    Un turno non ancora classificato (fascia=None, vedi TipoTurno) non entra
    in nessuna fascia: la persona compare comunque come "presente"
    nell'elenco, semplicemente non concorre al minimo finché il turno non
    viene classificato in Tipi turno. "non_classificati" conta quante di
    queste persone presenti restano fuori dal conteggio per questo motivo:
    senza saperlo, un minimo mattina/pomeriggio configurato ma con i turni
    reali ancora tutti non classificati risulterebbe sempre "sotto il
    minimo" anche a organico pieno, in modo silenzioso e fuorviante — vedi
    l'avviso in copertura.html quando questo numero non è zero."""
    conteggio = {"mattina": 0, "pomeriggio": 0}
    non_classificati = 0
    for riga in righe:
        if riga["stato"] != "presente":
            continue
        fascia = riga["assegnazione"].tipo_turno.fascia
        if fascia == "entrambe":
            conteggio["mattina"] += 1
            conteggio["pomeriggio"] += 1
        elif fascia in conteggio:
            conteggio[fascia] += 1
        else:
            non_classificati += 1
    conteggio["non_classificati"] = non_classificati
    return conteggio


def _costruisci_blocco(
    *,
    sede: Sede,
    nome_sottosezione: str | None,
    righe: list[dict],
    minimo_mattina: int,
    minimo_pomeriggio: int,
    copertura_aggiuntiva: int,
    sostituti_in_arrivo: list[Sostituzione],
    eventi_sede: list[EventoSala],
) -> dict:
    """Un blocco rappresenta o l'intera sede (nome_sottosezione=None: tutti i
    dipendenti di riferimento SENZA sottosezione) o un comparto interno con
    copertura monitorata a parte (es. "Parcheggio" dentro Valdina): stessa
    forma in entrambi i casi, così i template e le email non devono
    distinguere i due, vedi _raggruppa_per_sottosezione in
    app/routers/calendario.py per come i dipendenti vengono divisi tra i
    due. La copertura aggiuntiva per eventi nelle sale si applica solo al
    blocco della sede intera (le sale non appartengono a un comparto)."""
    presenti_per_fascia = _presenti_per_fascia(righe)
    presenti = sum(1 for r in righe if r["stato"] == "presente")

    richiesti_mattina = minimo_mattina + copertura_aggiuntiva
    richiesti_pomeriggio = minimo_pomeriggio + copertura_aggiuntiva
    sotto_minimo_mattina = richiesti_mattina > 0 and presenti_per_fascia["mattina"] < richiesti_mattina
    sotto_minimo_pomeriggio = richiesti_pomeriggio > 0 and presenti_per_fascia["pomeriggio"] < richiesti_pomeriggio

    return {
        "sede": sede,
        "nome_sottosezione": nome_sottosezione,
        "nome_visualizzato": f"{sede.nome} — {nome_sottosezione}" if nome_sottosezione else sede.nome,
        "righe": righe,
        "presenti": presenti,
        "totale": len(righe),
        "sostituti_in_arrivo": sostituti_in_arrivo,
        "eventi_oggi": eventi_sede,
        "presenti_mattina": presenti_per_fascia["mattina"],
        "presenti_pomeriggio": presenti_per_fascia["pomeriggio"],
        "presenti_non_classificati": presenti_per_fascia["non_classificati"],
        "copertura_minima_mattina": richiesti_mattina,
        "copertura_minima_pomeriggio": richiesti_pomeriggio,
        "sotto_minimo_mattina": sotto_minimo_mattina,
        "sotto_minimo_pomeriggio": sotto_minimo_pomeriggio,
        # Riassunto comodo per chi deve solo sapere "va bene o no" senza
        # distinguere le due fasce (es. il filtro dei blocchi da segnalare
        # nell'allarme copertura).
        "sotto_minimo": sotto_minimo_mattina or sotto_minimo_pomeriggio,
        "copertura_minima": richiesti_mattina + richiesti_pomeriggio,
    }


def calcola_copertura(db: Session, data_obj: date) -> list[dict]:
    """Per ogni sede attiva chi dei suoi dipendenti di riferimento è
    presente/assente/non pianificato in quella data, più i sostituti in
    arrivo — un blocco per la sede (dipendenti senza sottosezione) e un
    blocco ulteriore per ogni comparto con copertura monitorata a parte
    (Dipendente.sottosezione + SottosezioneCopertura, es. "Parcheggio"
    dentro Valdina): stessa forma di blocco in entrambi i casi. Usata sia
    dal cruscotto interattivo qui sotto sia dal riepilogo giornaliero via
    email e dall'allarme copertura: stessa identica logica in tutti i
    posti, non una copia parallela."""
    sedi = (
        db.query(Sede)
        .filter(Sede.attivo == True)  # noqa: E712
        .order_by(Sede.ordine_visualizzazione, Sede.nome)
        .all()
    )
    dipendenti = (
        db.query(Dipendente)
        .filter(Dipendente.attivo == True)  # noqa: E712
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )
    assegnazioni = {
        r.dipendente_id: r
        for r in db.query(AssegnazioneGiornaliera)
        .options(joinedload(AssegnazioneGiornaliera.tipo_turno))
        .filter(AssegnazioneGiornaliera.data == data_obj)
        .all()
    }
    sostituzioni_in_arrivo = (
        db.query(Sostituzione)
        .options(joinedload(Sostituzione.dipendente_sostituto), joinedload(Sostituzione.dipendente_partente))
        .filter(Sostituzione.data == data_obj)
        .all()
    )
    sostituti_per_sede_arrivo = {}
    for s in sostituzioni_in_arrivo:
        sostituti_per_sede_arrivo.setdefault(s.sede_arrivo_id, []).append(s)

    eventi_in_corso = (
        db.query(EventoSala)
        .options(joinedload(EventoSala.sala))
        .join(Sala)
        .filter(
            Sala.attivo == True,  # noqa: E712
            EventoSala.data_inizio <= data_obj,
            EventoSala.data_fine >= data_obj,
        )
        .all()
    )
    eventi_per_sede = {}
    for evento in eventi_in_corso:
        eventi_per_sede.setdefault(evento.sala.sede_id, []).append(evento)

    minimi_sottosezione = {
        (s.sede_id, chiave_sottosezione(s.nome)): s for s in db.query(SottosezioneCopertura).all()
    }

    blocchi = []
    for sede in sedi:
        dipendenti_sede = [d for d in dipendenti if d.sede_riferimento_id == sede.id]
        senza_sottosezione = [d for d in dipendenti_sede if not d.sottosezione]

        eventi_sede = eventi_per_sede.get(sede.id, [])
        sale_con_evento = {evento.sala_id: evento.sala for evento in eventi_sede}
        copertura_aggiuntiva = sum(sala.copertura_minima_aggiuntiva for sala in sale_con_evento.values())

        blocchi.append(_costruisci_blocco(
            sede=sede,
            nome_sottosezione=None,
            righe=_righe_presenza(senza_sottosezione, assegnazioni),
            minimo_mattina=sede.copertura_minima_mattina,
            minimo_pomeriggio=sede.copertura_minima_pomeriggio,
            copertura_aggiuntiva=copertura_aggiuntiva,
            sostituti_in_arrivo=sostituti_per_sede_arrivo.get(sede.id, []),
            eventi_sede=eventi_sede,
        ))

        gruppi_sottosezione: dict[str, list[Dipendente]] = {}
        for d in dipendenti_sede:
            if d.sottosezione:
                gruppi_sottosezione.setdefault(chiave_sottosezione(d.sottosezione), []).append(d)
        for chiave, membri in gruppi_sottosezione.items():
            minimo = minimi_sottosezione.get((sede.id, chiave))
            # Il nome del comparto (se configurato) vince su quello scritto
            # sul dipendente: così il titolo resta unico e corretto anche
            # se qualcuno lo ha digitato con maiuscole/spazi diversi.
            nome_sottosezione = minimo.nome if minimo else membri[0].sottosezione.strip()
            blocchi.append(_costruisci_blocco(
                sede=sede,
                nome_sottosezione=nome_sottosezione,
                righe=_righe_presenza(membri, assegnazioni),
                minimo_mattina=minimo.copertura_minima_mattina if minimo else 0,
                minimo_pomeriggio=minimo.copertura_minima_pomeriggio if minimo else 0,
                copertura_aggiuntiva=0,
                sostituti_in_arrivo=[],
                eventi_sede=[],
            ))

    # Per ogni blocco sotto il minimo, suggerisce chi tra i dipendenti degli
    # ALTRI palazzi non è pianificato quel giorno: un punto di partenza per
    # trovare una sostituzione, non un'assegnazione automatica (chi gestisce
    # i turni resta libero di scegliere chi spostare davvero). I comparti
    # (sottosezioni) attingono agli stessi non pianificati della propria
    # sede principale, per sede diversa dalla propria.
    non_pianificati_per_sede = {}
    for blocco in blocchi:
        if blocco["nome_sottosezione"] is not None:
            continue
        non_pianificati_per_sede[blocco["sede"].id] = [
            riga["dipendente"] for riga in blocco["righe"] if riga["stato"] == "non_pianificato"
        ]
    for blocco in blocchi:
        if not blocco["sotto_minimo"]:
            blocco["dipendenti_suggeriti"] = []
            continue
        blocco["dipendenti_suggeriti"] = [
            dip
            for sede_id, disponibili in non_pianificati_per_sede.items()
            if sede_id != blocco["sede"].id
            for dip in disponibili
        ]
    return blocchi


@router.get("/copertura")
def cruscotto_copertura(
    request: Request,
    data: str | None = None,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_LETTURA)),
):
    data_obj = _data_o_400(data) if data else date.today()
    blocchi = calcola_copertura(db, data_obj)

    return templates.TemplateResponse(
        request,
        "copertura.html",
        {
            "utente": utente,
            "data": data_obj,
            "blocchi": blocchi,
        },
    )

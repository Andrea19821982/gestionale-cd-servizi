from calendar import monthrange
from datetime import date

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session


def dipendenti_del_mese(db: Session, anno: int, mese: int):
    """Chi va conteggiato nel riepilogo di un mese: tutti gli attivi, più i
    disattivati che in quel mese hanno lavorato o sono stati assenti.

    Filtrare solo su attivo==True sembra ovvio e invece falsa i numeri: chi
    lascia l'azienda il 20 agosto sparisce anche dal riepilogo di agosto,
    il mese in cui ha lavorato venti giorni. Le sue ore e il suo costo non
    venivano sommati da nessuna parte, quindi il costo del lavoro del mese
    risultava più basso del vero — senza nessun avviso, e proprio quando si
    chiudono le buste paga.

    Chi stampa la riga distingue i disattivati guardando dipendente.attivo.
    """
    from app.models import AssegnazioneGiornaliera, Assenza, Dipendente

    primo = date(anno, mese, 1)
    ultimo = date(anno, mese, monthrange(anno, mese)[1])

    ha_turni = (
        db.query(AssegnazioneGiornaliera.dipendente_id)
        .filter(
            AssegnazioneGiornaliera.data >= primo,
            AssegnazioneGiornaliera.data <= ultimo,
        )
        .distinct()
    )
    ha_assenze = (
        db.query(Assenza.dipendente_id)
        .filter(
            Assenza.stato != "rifiutata",
            Assenza.data_inizio <= ultimo,
            Assenza.data_fine >= primo,
        )
        .distinct()
    )

    return (
        db.query(Dipendente)
        .filter(
            or_(
                Dipendente.attivo == True,  # noqa: E712
                Dipendente.id.in_(ha_turni),
                Dipendente.id.in_(ha_assenze),
            )
        )
        .order_by(Dipendente.cognome, Dipendente.nome)
        .all()
    )


def chiave_sottosezione(testo: str) -> str:
    """Normalizza il testo libero di Dipendente.sottosezione / Sotto­
    sezioneCopertura.nome per il confronto tra i due: senza questo, una
    differenza di maiuscole o di spazi (es. "Parcheggio" scritto come
    "parcheggio " su un dipendente) fa fallire silenziosamente
    l'abbinamento — il comparto perde il proprio minimo di copertura, o
    peggio si spacca in due gruppi distinti nella stessa sede. Successo
    reale: "Archivio Legislativo" nel comparto contro "Archivio
    legislativo" su 4 dipendenti, minimo mai applicato per mesi senza che
    nessuno se ne accorgesse."""
    return testo.strip().casefold()


def ottieni_o_404(db: Session, modello, id_valore):
    """Recupera un record per chiave primaria o solleva 404 invece di
    lasciare che un AttributeError su None finisca in un 500 non gestito
    (es. link/form rimasti aperti su un record nel frattempo eliminato)."""
    oggetto = db.get(modello, id_valore)
    if oggetto is None:
        raise HTTPException(status_code=404, detail=f"{modello.__name__} non trovato.")
    return oggetto


def checkbox_a_bool(valore: str | None) -> bool:
    """Un checkbox HTML non spuntato non compare affatto nel form inviato:
    il valore arriva come None, non come stringa vuota o 'off'."""
    return valore == "on"


def fk_opzionale_o_400(db: Session, modello, valore: str) -> int | None:
    """Converte il valore testuale di una <select> in un id valido, o solleva
    400 se non è un intero o non corrisponde a nessun record esistente.
    Stringa vuota -> None (campo facoltativo lasciato vuoto)."""
    if not valore:
        return None
    try:
        id_valore = int(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Valore non valido per {modello.__name__}.")
    if db.get(modello, id_valore) is None:
        raise HTTPException(
            status_code=400, detail=f"{modello.__name__} con id {id_valore} non trovato."
        )
    return id_valore

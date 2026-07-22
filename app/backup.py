"""Copia di sicurezza giornaliera del database SQLite: gira in un thread di
sfondo (vedi main.py) e non deve mai bloccare o interrompere il resto del
programma per un errore di I/O (disco pieno, cartella non scrivibile, ecc.)."""

import logging
import sqlite3
from datetime import date, datetime, time
from pathlib import Path

from app import config

logger = logging.getLogger("calendario_turni.backup")


def _ora_configurata_o_none(testo: str) -> time | None:
    try:
        return time.fromisoformat(testo)
    except ValueError:
        return None


def _backup_di_oggi_esiste() -> bool:
    """Un backup al giorno basta: il nome del file include già la data,
    quindi non serve una tabella dedicata solo per ricordare l'ultimo (a
    differenza del riepilogo giornaliero e dell'allarme di copertura, che
    devono tracciare a chi e cosa hanno inviato)."""
    if not config.BACKUP_CARTELLA.exists():
        return False
    prefisso = f"turni_{date.today().isoformat()}"
    return any(p.name.startswith(prefisso) for p in config.BACKUP_CARTELLA.iterdir())


def esegui_backup() -> Path | None:
    """Copia turni.db con l'API di backup di sqlite3 (sicura anche a
    database aperto e in scrittura, a differenza di una semplice copia del
    file) e rimuove i backup più vecchi della retenzione configurata.
    Restituisce il percorso del file creato, o None se non c'è ancora nessun
    database da copiare."""
    if not config.DB_PATH.exists():
        return None
    config.BACKUP_CARTELLA.mkdir(parents=True, exist_ok=True)
    nome_file = f"turni_{date.today().isoformat()}_{datetime.now().strftime('%H%M%S')}.db"
    destinazione = config.BACKUP_CARTELLA / nome_file

    origine = sqlite3.connect(str(config.DB_PATH))
    try:
        copia = sqlite3.connect(str(destinazione))
        try:
            origine.backup(copia)
        finally:
            copia.close()
    finally:
        origine.close()

    _pulisci_backup_vecchi()
    return destinazione


def _pulisci_backup_vecchi() -> None:
    if not config.BACKUP_CARTELLA.exists():
        return
    limite_timestamp = datetime.now().timestamp() - config.BACKUP_RETENZIONE_GIORNI * 86400
    for percorso in config.BACKUP_CARTELLA.glob("turni_*.db"):
        try:
            if percorso.stat().st_mtime < limite_timestamp:
                percorso.unlink()
        except OSError:
            logger.exception("Impossibile eliminare il backup vecchio %s", percorso)


def controlla_e_backup_se_dovuto() -> bool:
    """Da chiamare periodicamente da un thread di sfondo (vedi main.py): non
    fa nulla se il backup automatico non è abilitato, se non è ancora l'ora
    configurata, o se è già stato fatto oggi. Non solleva mai eccezioni."""
    try:
        if not config.BACKUP_ABILITATO:
            return False
        ora_configurata = _ora_configurata_o_none(config.BACKUP_ORA)
        if ora_configurata is None:
            logger.error("BACKUP_ORA non valido: %r", config.BACKUP_ORA)
            return False
        if datetime.now().time() < ora_configurata:
            return False
        if _backup_di_oggi_esiste():
            return False
        return esegui_backup() is not None
    except Exception:
        logger.exception("Backup automatico del database fallito")
        return False

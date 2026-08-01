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


def _problema_di_integrita(percorso: Path) -> str | None:
    """Restituisce il problema riscontrato, o None se il file è un database
    sano e leggibile."""
    try:
        con = sqlite3.connect(str(percorso))
        try:
            esito = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as e:
        return str(e)
    return None if esito == "ok" else esito


def esegui_backup() -> Path | None:
    """Copia turni.db con l'API di backup di sqlite3 (sicura anche a
    database aperto e in scrittura, a differenza di una semplice copia del
    file) e rimuove i backup più vecchi della retenzione configurata.
    Restituisce il percorso del file creato, o None se non c'è nessun
    database da copiare o se la copia non è risultata sana.

    La copia viene riletta e verificata prima di essere tenuta buona. Un
    backup rovinato è peggio di nessun backup: sembra una via di scampo e
    non lo è, e ci si accorge che non lo era proprio nel momento in cui
    serviva. Se la verifica fallisce, la copia viene buttata e soprattutto
    NON si passa a _pulisci_backup_vecchi(): i backup buoni di prima
    restano dove sono, che è esattamente ciò che serve quando il database
    in uso è danneggiato."""
    if not config.DB_PATH.exists():
        return None
    config.BACKUP_CARTELLA.mkdir(parents=True, exist_ok=True)
    nome_file = f"turni_{date.today().isoformat()}_{datetime.now().strftime('%H%M%S')}.db"
    destinazione = config.BACKUP_CARTELLA / nome_file

    try:
        origine = sqlite3.connect(str(config.DB_PATH))
        try:
            copia = sqlite3.connect(str(destinazione))
            try:
                origine.backup(copia)
            finally:
                copia.close()
        finally:
            origine.close()
    except sqlite3.Error:
        logger.exception("Backup del database non riuscito: %s", config.DB_PATH)
        destinazione.unlink(missing_ok=True)
        return None

    problema = _problema_di_integrita(destinazione)
    if problema is not None:
        logger.error(
            "Backup scartato perché non integro (%s): quasi sempre vuol dire che è danneggiato "
            "il database in uso, %s. I backup precedenti NON sono stati toccati: ripristina "
            "l'ultimo buono da %s.",
            problema, config.DB_PATH, config.BACKUP_CARTELLA,
        )
        destinazione.unlink(missing_ok=True)
        return None

    _pulisci_backup_vecchi()
    return destinazione


def _pulisci_backup_vecchi() -> None:
    """Toglie i backup più vecchi della retenzione, ma non scende mai sotto
    BACKUP_MINIMI_DA_CONSERVARE copie.

    Il solo criterio dell'età non basta: i backup si fanno quando il server
    è acceso, quindi in un periodo di fermo (ferie d'agosto, un PC server
    cambiato, il programma riaperto dopo settimane) la cartella si
    svuoterebbe da sola proprio mentre nessuno stava guardando, lasciando
    zero copie. Tenere comunque le ultime N costa pochi megabyte ed è
    l'unica cosa che conta il giorno in cui servono."""
    if not config.BACKUP_CARTELLA.exists():
        return
    limite_timestamp = datetime.now().timestamp() - config.BACKUP_RETENZIONE_GIORNI * 86400
    try:
        backup = sorted(
            config.BACKUP_CARTELLA.glob("turni_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        logger.exception("Impossibile elencare i backup in %s", config.BACKUP_CARTELLA)
        return

    for percorso in backup[config.BACKUP_MINIMI_DA_CONSERVARE:]:
        try:
            if percorso.stat().st_mtime < limite_timestamp:
                percorso.unlink()
        except OSError:
            logger.exception("Impossibile eliminare il backup vecchio %s", percorso)


_giorno_ultimo_tentativo_fallito: date | None = None


def controlla_e_backup_se_dovuto() -> bool:
    """Da chiamare periodicamente da un thread di sfondo (vedi main.py): non
    fa nulla se il backup automatico non è abilitato, se non è ancora l'ora
    configurata, o se è già stato fatto oggi. Non solleva mai eccezioni.

    Un tentativo fallito conta come "fatto per oggi": il ciclo chiama questa
    funzione ogni minuto, e senza questa memoria un database danneggiato
    farebbe ripartire una copia completa (e riempire il log dello stesso
    errore) sessanta volte l'ora, per tutto il giorno."""
    global _giorno_ultimo_tentativo_fallito
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
        if _giorno_ultimo_tentativo_fallito == date.today():
            return False
        if esegui_backup() is not None:
            return True
        _giorno_ultimo_tentativo_fallito = date.today()
        return False
    except Exception:
        logger.exception("Backup automatico del database fallito")
        _giorno_ultimo_tentativo_fallito = date.today()
        return False

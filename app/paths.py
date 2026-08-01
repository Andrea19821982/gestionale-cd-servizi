"""Percorsi consapevoli della modalità di esecuzione: script Python in
sviluppo oppure eseguibile impacchettato con PyInstaller.

Una volta impacchettato, il codice gira da una cartella temporanea di
estrazione (sys._MEIPASS): lì dentro deve stare solo cosa è di sola lettura
(template, static).

I dati che il programma scrive (database, allegati, backup, chiave di
sessione, log) NON stanno accanto all'eseguibile ma in una cartella
dedicata sotto %LOCALAPPDATA%\\CD-Servizi. Il motivo è l'installer: la
cartella del programma è gestita dal setup, che ne sovrascrive il contenuto
ad ogni aggiornamento e la rimuove alla disinstallazione. Tenere il
database lì dentro significherebbe che un aggiornamento, o una
disinstallazione fatta per sbaglio, si porta via i turni di tutti.
Separando i due posti la cartella del programma diventa usa e getta, e i
dati sopravvivono a qualunque reinstallazione.

Le versioni precedenti scrivevano davvero accanto all'eseguibile, quindi al
primo avvio i dati già esistenti vengono recuperati da lì: vedi
_migra_dati_dalla_cartella_eseguibile().
"""

import os
import shutil
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

# Sottocartella comune a tutti i programmi CD Servizi, così i dati di
# questo programma non finiscono sparsi nella radice di LOCALAPPDATA.
_CARTELLA_PRODUTTORE = "CD-Servizi"

_CARTELLA_DATI_SERVER = "CalendarioTurni-Server"
_CARTELLA_DATI_CLIENT = "CalendarioTurni"

# Cosa recuperare dalla vecchia posizione (accanto all'eseguibile) la prima
# volta che si parte con questa versione.
#
# ATTENZIONE, qui c'è stata una perdita di dati vera: in origine questa lista
# comprendeva anche "turni.db-wal" e "turni.db-shm", perché sono la parte di
# transazioni non ancora consolidata nel file principale (SQLite è in
# modalità WAL, vedi app/database.py) e sembrava che copiare il solo
# turni.db perdesse le ultime modifiche.
#
# Il problema è che venivano copiati come tre voci INDIPENDENTI, mentre la
# guardia qui sotto salta ciò che la destinazione ha già. Se la destinazione
# aveva il suo turni.db (saltato, giustamente) ma in quel momento nessun
# -wal — cioè la situazione normale dopo una chiusura pulita — allora il
# -wal della VECCHIA installazione le veniva innestato accanto. SQLite lo
# applica come se fosse suo, e il database sano assume in silenzio il
# contenuto di quello vecchio: senza errori, e superando pure
# PRAGMA integrity_check. Vedi tests/test_migrazione_dati.py.
#
# Il database ora si copia con l'API di backup di sqlite3 (_copia_database),
# che consolida da sé l'eventuale -wal dell'origine dentro la copia: le
# ultime modifiche non si perdono lo stesso, e nessun -wal estraneo può
# più finire accanto a un database che non è il suo.
_NOME_DATABASE = "turni.db"

_DATI_SERVER_DA_MIGRARE = (
    _NOME_DATABASE,
    "secret_key.txt",
    "indirizzo_server.txt",
    "allegati",
    "backup",
)

_DATI_CLIENT_DA_MIGRARE = ("client_config.json",)

# La migrazione va fatta una volta sola, ma non può basarsi sull'esistenza
# del database: quello viene creato comunque al primo avvio, anche da zero,
# quando non c'è nulla da recuperare. Serve un segnaposto esplicito.
_NOME_MARCATORE = ".dati_migrati"


def _impacchettato() -> bool:
    return bool(getattr(sys, "frozen", False))


def _radice_progetto() -> Path:
    return Path(__file__).resolve().parent.parent


def _cartella_eseguibile() -> Path:
    return Path(sys.executable).resolve().parent


def _cartelle_installazioni_precedenti(nome_vecchia_cartella: str) -> list[Path]:
    """Dove cercare i dati delle installazioni fatte prima dell'installer.

    Gli script installa_client.ps1 / installa_server.ps1 copiavano il
    programma in %LOCALAPPDATA%\\Programs\\CalendarioTurni[-Server] e i dati
    finivano lì dentro, accanto all'eseguibile. L'installer invece usa una
    cartella sua, quindi il solo controllo "accanto all'eseguibile" non
    troverebbe niente e il server ripartirebbe con un database vuoto pur
    avendo i turni di tutti sul disco, a due cartelle di distanza.
    """
    radice = os.environ.get("LOCALAPPDATA")
    if not radice:
        return []
    return [Path(radice) / "Programs" / nome_vecchia_cartella]


def _copia_database(da: Path, a: Path) -> None:
    """Copia un database SQLite con l'API di backup di sqlite3 invece che
    come file qualunque: l'eventuale -wal dell'origine viene consolidato
    dentro la copia, che nasce quindi completa e autosufficiente. Così non
    serve (e non si deve) copiare separatamente -wal e -shm, che accanto a
    un database diverso dal proprio ne sostituiscono in silenzio il
    contenuto — vedi il commento su _DATI_SERVER_DA_MIGRARE."""
    origine = sqlite3.connect(str(da))
    try:
        copia = sqlite3.connect(str(a))
        try:
            origine.backup(copia)
        finally:
            copia.close()
    finally:
        origine.close()


def _migra_dati(
    destinazione: Path, contenuti: tuple[str, ...], origini: list[Path]
) -> None:
    """Recupera i dati delle versioni precedenti la prima volta che si parte
    con la cartella dati nuova, provando le possibili vecchie posizioni in
    ordine: vince la prima che contiene qualcosa.

    Copia invece di spostare: se qualcosa va storto a metà (disco pieno,
    file tenuto aperto da un antivirus) gli originali restano dove sono,
    invece di lasciare l'utente con il database a metà in entrambi i posti.
    Le copie vecchie non danno fastidio, quelle cartelle non vengono più
    lette.
    """
    marcatore = destinazione / _NOME_MARCATORE
    if marcatore.exists():
        return

    for origine in origini:
        if origine == destinazione or not origine.is_dir():
            continue
        if not any((origine / nome).exists() for nome in contenuti):
            continue  # cartella vuota o già svuotata: prova la prossima

        for nome in contenuti:
            da = origine / nome
            a = destinazione / nome
            # Quello che c'è già nella destinazione ha la precedenza: è il
            # file in uso adesso, non va sovrascritto con una copia vecchia
            # rimasta in giro.
            if not da.exists() or a.exists():
                continue
            try:
                if nome == _NOME_DATABASE:
                    _copia_database(da, a)
                elif da.is_dir():
                    shutil.copytree(da, a)
                else:
                    shutil.copy2(da, a)
            except (OSError, sqlite3.Error):
                # Senza marcatore la migrazione viene ritentata al prossimo
                # avvio, e i file già copiati li salta il controllo qui
                # sopra: meglio riprovare che dare per concluso un recupero
                # rimasto a metà.
                return
        break  # i dati sono stati recuperati: non guardare le altre origini

    try:
        marcatore.write_text(
            "Questa cartella contiene i dati di Gestionale CD Servizi.\n"
            "Il file serve al programma per sapere che i dati delle versioni\n"
            "precedenti sono già stati recuperati: non cancellarlo.\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # si ritenterà al prossimo avvio, senza rompere nulla


def _cartella_dati_utente(nome: str, contenuti: tuple[str, ...]) -> Path:
    radice = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    cartella = Path(radice) / _CARTELLA_PRODUTTORE / nome
    cartella.mkdir(parents=True, exist_ok=True)
    origini = [_cartella_eseguibile(), *_cartelle_installazioni_precedenti(nome)]
    _migra_dati(cartella, contenuti, origini)
    return cartella


@lru_cache(maxsize=None)
def cartella_dati() -> Path:
    """Cartella scrivibile del server: %LOCALAPPDATA%\\CD-Servizi\\... se
    impacchettato, radice del progetto in sviluppo.

    In cache perché viene chiamata all'import da più moduli (app/config.py,
    server_app.py): la cartella va creata, e la migrazione tentata, una
    volta sola per avvio e non ad ogni chiamata.
    """
    if not _impacchettato():
        return _radice_progetto()
    return _cartella_dati_utente(_CARTELLA_DATI_SERVER, _DATI_SERVER_DA_MIGRARE)


@lru_cache(maxsize=None)
def cartella_dati_client() -> Path:
    """Cartella scrivibile del client (solo client_config.json, con
    l'indirizzo del server): separata da quella del server perché sui PC dei
    colleghi il server non c'è, e sul PC dell'ufficio i due programmi
    convivono senza mescolare i propri file."""
    if not _impacchettato():
        return _radice_progetto()
    return _cartella_dati_utente(_CARTELLA_DATI_CLIENT, _DATI_CLIENT_DA_MIGRARE)


def cartella_risorse() -> Path:
    """Cartella di sola lettura per template/static: dentro il bundle
    PyInstaller se impacchettato, radice del progetto in sviluppo."""
    if _impacchettato():
        return Path(sys._MEIPASS)
    return _radice_progetto()

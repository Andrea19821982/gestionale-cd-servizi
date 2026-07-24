import secrets
import threading
from datetime import date, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DelegaApprovazione, Utente

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Definiti una sola volta qui e importati nei router, così un ruolo aggiunto
# per errore a una tupla di sola lettura o di scrittura non può diventare
# una copia locale disallineata dal resto dell'app.
RUOLI_LETTURA = ("amministratore", "gestore_turni", "consultazione")
RUOLI_SCRITTURA_ANAGRAFICA = ("amministratore",)  # sedi e tipi turno: dati strutturali
RUOLI_SCRITTURA_OPERATIVO = ("amministratore", "gestore_turni")  # dipendenti e calendario
RUOLI_APPROVAZIONE = ("amministratore",)  # approvare/rifiutare richieste di assenza


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


# Hash "fittizio" con cui confrontare la password quando lo username non
# esiste: bcrypt è apposta lento (decine/centinaia di ms), quindi se si
# saltasse la verifica per uno username inesistente la risposta arriverebbe
# sempre più veloce di quella per uno username esistente con password
# sbagliata. Quella differenza di tempo misurabile è un side-channel che
# permetterebbe di scoprire quali username esistono senza nemmeno provare a
# indovinarne la password (enumerazione utenti): eseguendo comunque il
# confronto, con un hash qualsiasi, il tempo di risposta resta lo stesso in
# entrambi i casi.
_HASH_FITTIZIO_PER_TEMPO_COSTANTE = hash_password(secrets.token_hex(32))


def autentica(db: Session, username: str, password: str) -> Utente | None:
    utente = db.query(Utente).filter(Utente.username == username, Utente.attivo == True).first()  # noqa: E712
    hash_da_verificare = utente.password_hash if utente is not None else _HASH_FITTIZIO_PER_TEMPO_COSTANTE
    password_corretta = verify_password(password, hash_da_verificare)
    if utente is None or not password_corretta:
        return None
    return utente


# --- Blocco tentativi di login falliti (anti-bruteforce) ---
# Contatore in memoria per username, non persistito: si azzera a ogni
# riavvio del server, il che va benissimo per questo scopo (rallentare chi
# indovina password a tentativi, non serve un registro permanente).
MASSIMO_TENTATIVI_LOGIN = 5
BLOCCO_LOGIN_MINUTI = 5

_tentativi_falliti: dict[str, tuple[int, datetime | None]] = {}
_lock_tentativi_falliti = threading.Lock()


def minuti_blocco_login_residui(username: str) -> float:
    """0 se l'username può ritentare subito, altrimenti i minuti ancora da
    aspettare prima del prossimo tentativo utile."""
    with _lock_tentativi_falliti:
        voce = _tentativi_falliti.get(username)
        if voce is None:
            return 0.0
        _, bloccato_fino = voce
        if bloccato_fino is None or bloccato_fino <= datetime.now():
            return 0.0
        return (bloccato_fino - datetime.now()).total_seconds() / 60


def registra_tentativo_login(username: str, riuscito: bool) -> None:
    """Da chiamare dopo ogni tentativo di login, riuscito o no: un login
    riuscito azzera il contatore, uno fallito lo incrementa e blocca
    temporaneamente l'username dopo troppi fallimenti consecutivi."""
    with _lock_tentativi_falliti:
        if riuscito:
            _tentativi_falliti.pop(username, None)
            return
        conteggio, _ = _tentativi_falliti.get(username, (0, None))
        conteggio += 1
        bloccato_fino = (
            datetime.now() + timedelta(minutes=BLOCCO_LOGIN_MINUTI)
            if conteggio >= MASSIMO_TENTATIVI_LOGIN
            else None
        )
        _tentativi_falliti[username] = (conteggio, bloccato_fino)


class NonAutenticato(Exception):
    """Sollevata quando una route protetta viene chiamata senza sessione valida.
    Un exception handler in main.py la trasforma in un redirect a /login."""


def get_utente_corrente(request: Request, db: Session = Depends(get_db)) -> Utente:
    utente_id = request.session.get("utente_id")
    if utente_id is None:
        raise NonAutenticato()
    utente = db.get(Utente, utente_id)
    if utente is None or not utente.attivo:
        request.session.clear()
        raise NonAutenticato()
    return utente


def richiedi_ruolo(*ruoli_ammessi: str):
    def dependency(utente: Utente = Depends(get_utente_corrente)) -> Utente:
        if utente.ruolo not in ruoli_ammessi:
            raise HTTPException(status_code=403, detail="Permesso negato per questo ruolo.")
        return utente

    return dependency


def puo_approvare_assenze(db: Session, utente: Utente) -> bool:
    """Un amministratore può sempre approvare/rifiutare; chiunque altro solo
    se ha una delega attiva oggi (es. il capo è in ferie e ha delegato un
    gestore_turni per quel periodo). Un ruolo "dipendente" non può mai
    approvare, nemmeno con una delega: la creazione della delega lo impedisce
    già (vedi /deleghe/nuova), ma un utente delegato può essere degradato a
    "dipendente" *dopo* aver ricevuto la delega, che altrimenti resterebbe
    valida fino alla sua scadenza nonostante il ruolo ormai troppo basso."""
    if utente.ruolo == "amministratore":
        return True
    if utente.ruolo == "dipendente":
        return False
    oggi = date.today()
    delega = (
        db.query(DelegaApprovazione)
        .filter(
            DelegaApprovazione.utente_delegato_id == utente.id,
            DelegaApprovazione.data_inizio <= oggi,
            DelegaApprovazione.data_fine >= oggi,
        )
        .first()
    )
    return delega is not None


def richiedi_approvatore(
    utente: Utente = Depends(get_utente_corrente), db: Session = Depends(get_db)
) -> Utente:
    if not puo_approvare_assenze(db, utente):
        raise HTTPException(status_code=403, detail="Permesso negato: non puoi approvare o rifiutare richieste di assenza.")
    return utente

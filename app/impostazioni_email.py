"""Configurazione IMAP effettiva: legge prima la tabella impostazioni_imap
(modificabile dall'amministratore in /bozze-email), e solo se quella riga
manca o ha i campi vuoti ricade sui valori statici di app/email_config.py.
Così chi gestisce il programma può cambiare la casella email da cui leggere
le richieste dei dipendenti direttamente dall'interfaccia, senza dover
editare file sul PC server, restando comunque compatibile con chi preferisce
ancora compilare email_config_locale.py a mano."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app import email_config
from app.models import ImpostazioneImap


@dataclass
class ImapEffettivo:
    host: str
    porta: int
    utente: str
    password: str
    cartella: str


def _riga(db: Session) -> ImpostazioneImap | None:
    return db.get(ImpostazioneImap, 1)


def campi_grezzi(db: Session) -> tuple[str, int, str, str, bool]:
    """Host, porta, utente, cartella e se una password è salvata, così come
    sono davvero in DB (non i valori effettivi sopra, che includono il
    ripiego sul file quando la riga è incompleta): servono a precompilare
    il form di modifica con quello che è stato davvero salvato da
    interfaccia, non con valori presi dal file che sembrerebbero già
    salvati se mostrati lì.

    Scenario reale che questo evita: l'ufficio cambia casella email,
    compila Host+Indirizzo nuovi ma lascia la Password vuota (il
    placeholder dice "lascia vuoto per non cambiarla" — ragionevole,
    perché è vero per la password). Con imap_effettivo(), che ricade sul
    file finché password non è valorizzata anche lei, l'intera riga resta
    ignorata: host e utente nuovi sembrano salvati ma non vengono mai
    usati, e riaprendo la pagina il form mostrerebbe di nuovo i vecchi
    valori del file, come se il salvataggio non fosse avvenuto."""
    riga = _riga(db)
    if riga is None:
        return "", 993, "", "", False
    return riga.host or "", riga.porta, riga.utente or "", riga.cartella or "", bool(riga.password)


def imap_effettivo(db: Session) -> ImapEffettivo:
    riga = _riga(db)
    if riga and riga.host and riga.utente and riga.password:
        return ImapEffettivo(riga.host, riga.porta, riga.utente, riga.password, riga.cartella or "INBOX")
    return ImapEffettivo(
        email_config.IMAP_HOST,
        email_config.IMAP_PORTA,
        email_config.IMAP_UTENTE,
        email_config.IMAP_PASSWORD,
        email_config.IMAP_CARTELLA,
    )


def salva_impostazioni(
    db: Session,
    utente_id: int,
    host: str,
    porta: int,
    utente: str,
    password: str,
    cartella: str,
) -> None:
    """Password vuota = non toccare quella già salvata (evita di dover
    riscrivere la password ogni volta che si cambia solo un altro campo).

    NON fa commit: lo fa il chiamante, come per registra_modifica (vedi
    app/logging_service.py). Prima committava qui dentro, e il router che
    registrava la modifica nel log SUBITO DOPO si ritrovava la riga di log
    in una transazione che non veniva mai chiusa: veniva scartata alla
    chiusura della sessione, quindi il cambio della casella email non
    risultava a nessuno pur sembrando tracciato."""
    riga = _riga(db)
    if riga is None:
        riga = ImpostazioneImap(id=1)
        db.add(riga)
    riga.host = host.strip()
    riga.porta = porta
    riga.utente = utente.strip()
    if password:
        riga.password = password
    riga.cartella = cartella.strip() or "INBOX"
    riga.aggiornato_il = datetime.now()
    riga.aggiornato_da = utente_id

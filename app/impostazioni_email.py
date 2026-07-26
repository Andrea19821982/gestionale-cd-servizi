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

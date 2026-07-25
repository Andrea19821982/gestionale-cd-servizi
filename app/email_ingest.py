"""Lettura automatica delle email di assenza/sostituzione mandate dai
dipendenti (vedi docs/06-formato-email-dipendenti.md per il formato atteso).

Due responsabilità separate in questo modulo:
- analizza_email(): interpreta oggetto+corpo di UNA email e restituisce i
  campi trovati, senza mai sollevare eccezioni né inventare dati quando
  qualcosa non è chiaro (in quel caso valorizza solo "errore_parsing").
- controlla_posta(): si collega alla casella IMAP configurata, legge le
  email non lette e crea una BozzaEmail per ciascuna (mai la vera
  Assenza/Sostituzione: quella nasce solo alla conferma umana, vedi
  app/routers/bozze_email.py).
"""

import email as email_lib
import imaplib
import logging
import re
from datetime import date, datetime, time
from email.header import decode_header

from sqlalchemy.orm import Session

from app import impostazioni_email
from app.database import SessionLocal
from app.models import BozzaEmail, Dipendente

logger = logging.getLogger("calendario_turni.email_ingest")

_RIGA_CAMPO = re.compile(r"^\s*([^:]+):\s*(.*)$")


def _estrai_campi(corpo: str) -> dict[str, str]:
    """Righe 'Etichetta: valore' del corpo email -> dict con etichette
    normalizzate (minuscolo, spazi tolleranti) come chiave."""
    campi: dict[str, str] = {}
    for riga in corpo.splitlines():
        m = _RIGA_CAMPO.match(riga)
        if not m:
            continue
        etichetta = m.group(1).strip().lower()
        valore = m.group(2).strip()
        campi[etichetta] = valore
    return campi


def _data_o_none(testo: str) -> date | None:
    testo = (testo or "").strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(testo, formato).date()
        except ValueError:
            continue
    return None


def _ora_o_none(testo: str) -> time | None:
    testo = (testo or "").strip()
    if not testo:
        return None
    try:
        return time.fromisoformat(testo)
    except ValueError:
        return None


def _campo(campi: dict[str, str], *etichette: str) -> str:
    """Prima etichetta tra quelle indicate che compare nel corpo email, es.
    _campo(campi, "nome", "nome e cognome"): il modulo Word ufficiale (vedi
    static/documenti/Procedura_Segnalazione_Assenze_CD-Servizi.docx) usa
    "Nome e Cognome:" come etichetta del campo da compilare, mentre la guida
    testuale storica (genera_testo_email_dipendenti) usa solo "Nome:" —
    entrambe devono essere lette allo stesso modo, senza costringere chi
    scrive l'email a indovinare quale delle due si aspetta il programma."""
    for etichetta in etichette:
        valore = campi.get(etichetta)
        if valore:
            return valore
    return ""


def _trova_dipendente(db: Session, testo: str) -> tuple[Dipendente | None, str | None]:
    """Cerca un dipendente attivo il cui "cognome nome" o "nome cognome"
    corrisponda al testo (case-insensitive, spazi tolleranti). Se non trova
    esattamente un risultato univoco restituisce (None, messaggio da
    mostrare a chi rivede la bozza): non tenta mai un match approssimato,
    per non collegare l'assenza alla persona sbagliata."""
    testo_norm = " ".join((testo or "").split()).lower()
    if not testo_norm:
        return None, "nome mancante"

    candidati = db.query(Dipendente).filter(Dipendente.attivo == True).all()  # noqa: E712
    trovati = [
        d for d in candidati
        if f"{d.cognome} {d.nome}".lower() == testo_norm or f"{d.nome} {d.cognome}".lower() == testo_norm
    ]
    if len(trovati) == 1:
        return trovati[0], None
    if len(trovati) == 0:
        return None, f"dipendente non trovato: {testo!r}"
    return None, f"più dipendenti corrispondono a {testo!r}"


def analizza_email(db: Session, oggetto: str, corpo: str) -> dict:
    """Restituisce un dict con i campi pronti per una BozzaEmail. "tipo" è
    None se l'oggetto non contiene ASSENZA né SOSTITUZIONE (email non
    pertinente, va ignorata dal chiamante). "errore_parsing" riassume gli
    avvisi (dipendente non trovato, data mancante, ...) o è None se tutto è
    stato interpretato senza ambiguità."""
    oggetto_norm = (oggetto or "").upper()
    campi = _estrai_campi(corpo or "")
    avvisi: list[str] = []

    if "SOSTITUZIONE" in oggetto_norm:
        tipo = "sostituzione"
    elif "ASSENZA" in oggetto_norm:
        tipo = "assenza"
    else:
        return {"tipo": None}

    risultato = {
        "tipo": tipo,
        "dipendente_id": None,
        "dipendente_sostituto_id": None,
        "tipo_assenza": None,
        "data_inizio": None,
        "data_fine": None,
        "ora_inizio": None,
        "ora_fine": None,
        "note": None,
    }

    if tipo == "assenza":
        dipendente, errore = _trova_dipendente(db, _campo(campi, "nome", "nome e cognome"))
        if errore:
            avvisi.append(errore)
        risultato["dipendente_id"] = dipendente.id if dipendente else None

        risultato["tipo_assenza"] = campi.get("tipo") or None
        if not risultato["tipo_assenza"]:
            avvisi.append("tipo di assenza mancante")

        dal = _data_o_none(campi.get("dal", ""))
        al = _data_o_none(campi.get("al", ""))
        if dal is None:
            avvisi.append(f"data 'Dal' mancante o non valida: {campi.get('dal', '')!r}")
        if al is None:
            avvisi.append(f"data 'Al' mancante o non valida: {campi.get('al', '')!r}")
        if dal and al and al < dal:
            avvisi.append("la data 'Al' precede la data 'Dal'")
        risultato["data_inizio"] = dal
        risultato["data_fine"] = al
        risultato["note"] = campi.get("note") or None

    else:  # sostituzione
        assente, errore_assente = _trova_dipendente(db, campi.get("assente", ""))
        if errore_assente:
            avvisi.append(f"assente: {errore_assente}")
        sostituto, errore_sostituto = _trova_dipendente(db, campi.get("sostituto", ""))
        if errore_sostituto:
            avvisi.append(f"sostituto: {errore_sostituto}")
        if assente and sostituto and assente.id == sostituto.id:
            avvisi.append("assente e sostituto coincidono")
            sostituto = None
        risultato["dipendente_id"] = assente.id if assente else None
        risultato["dipendente_sostituto_id"] = sostituto.id if sostituto else None

        data_sost = _data_o_none(campi.get("data", ""))
        if data_sost is None:
            avvisi.append(f"data mancante o non valida: {campi.get('data', '')!r}")
        risultato["data_inizio"] = data_sost
        risultato["data_fine"] = data_sost

        orario = (campi.get("orario") or "").strip().lower()
        if orario and orario != "intera giornata":
            if "-" in orario:
                inizio_testo, _, fine_testo = orario.partition("-")
                inizio = _ora_o_none(inizio_testo.strip())
                fine = _ora_o_none(fine_testo.strip())
                if inizio is None or fine is None:
                    avvisi.append(f"orario non riconosciuto: {campi.get('orario', '')!r}")
                else:
                    risultato["ora_inizio"] = inizio
                    risultato["ora_fine"] = fine
            else:
                avvisi.append(f"orario non riconosciuto: {campi.get('orario', '')!r}")

    risultato["errore_parsing"] = "; ".join(avvisi) if avvisi else None
    return risultato


def _decodifica_header(valore: str) -> str:
    parti = decode_header(valore or "")
    risultato = ""
    for testo, codifica in parti:
        if isinstance(testo, bytes):
            risultato += testo.decode(codifica or "utf-8", errors="replace")
        else:
            risultato += testo
    return risultato


def _corpo_testo(messaggio) -> str:
    if messaggio.is_multipart():
        for parte in messaggio.walk():
            if parte.get_content_type() == "text/plain" and not parte.get_filename():
                charset = parte.get_content_charset() or "utf-8"
                contenuto = parte.get_payload(decode=True) or b""
                return contenuto.decode(charset, errors="replace")
        return ""
    charset = messaggio.get_content_charset() or "utf-8"
    contenuto = messaggio.get_payload(decode=True) or b""
    return contenuto.decode(charset, errors="replace")


def _elabora_messaggio(db: Session, imap: imaplib.IMAP4_SSL, numero: bytes) -> bool:
    """Restituisce True se ha creato una bozza (email pertinente). Fa il
    commit di QUESTA bozza prima di segnare l'email come letta: se si
    marcasse \\Seen prima e il commit fallisse dopo (per un'altra email nello
    stesso giro), l'email sparirebbe letta ma senza nessuna bozza salvata,
    persa per sempre al giro successivo."""
    stato, dati = imap.fetch(numero, "(RFC822)")
    if stato != "OK" or not dati or dati[0] is None:
        return False
    messaggio = email_lib.message_from_bytes(dati[0][1])
    mittente = _decodifica_header(messaggio.get("From", ""))
    oggetto = _decodifica_header(messaggio.get("Subject", ""))
    corpo = _corpo_testo(messaggio)

    risultato = analizza_email(db, oggetto, corpo)
    if risultato.get("tipo") is None:
        # Email non pertinente (oggetto senza ASSENZA/SOSTITUZIONE): la si
        # lascia non letta, non è compito nostro nasconderla dalla casella.
        return False

    db.add(BozzaEmail(
        tipo=risultato["tipo"],
        mittente=mittente,
        oggetto=oggetto,
        corpo=corpo,
        errore_parsing=risultato.get("errore_parsing"),
        dipendente_id=risultato.get("dipendente_id"),
        dipendente_sostituto_id=risultato.get("dipendente_sostituto_id"),
        tipo_assenza=risultato.get("tipo_assenza"),
        data_inizio=risultato.get("data_inizio"),
        data_fine=risultato.get("data_fine"),
        ora_inizio=risultato.get("ora_inizio"),
        ora_fine=risultato.get("ora_fine"),
        note=risultato.get("note"),
    ))
    db.commit()
    imap.store(numero, "+FLAGS", "\\Seen")
    return True


def controlla_posta() -> int:
    """Si collega alla casella IMAP configurata (da /bozze-email o, in
    mancanza, da app/email_config.py — vedi app/impostazioni_email.py),
    legge le email non lette e crea una BozzaEmail per ciascuna email
    pertinente. Non fa nulla se l'IMAP non è configurato da nessuna delle
    due parti. Non solleva mai eccezioni verso il chiamante: un problema di
    connessione o su una singola email viene solo registrato nei log, il
    resto continua."""
    db = SessionLocal()
    create = 0
    try:
        cfg = impostazioni_email.imap_effettivo(db)
        if not (cfg.host and cfg.utente and cfg.password):
            return 0
        with imaplib.IMAP4_SSL(cfg.host, cfg.porta) as imap:
            imap.login(cfg.utente, cfg.password)
            imap.select(cfg.cartella)
            stato, dati = imap.search(None, "UNSEEN")
            if stato != "OK" or not dati or not dati[0]:
                return 0
            for numero in dati[0].split():
                try:
                    if _elabora_messaggio(db, imap, numero):
                        create += 1
                except Exception:
                    logger.exception("Errore nell'elaborazione di un'email (numero=%r)", numero)
                    # Il commit della bozza è già per-email (vedi
                    # _elabora_messaggio): se questa è fallita, la sessione va
                    # ripulita prima di passare alla prossima, altrimenti
                    # SQLAlchemy rifiuta qualunque altra operazione finché non
                    # viene fatto un rollback esplicito.
                    db.rollback()
    except Exception:
        logger.exception("Controllo posta IMAP fallito")
        db.rollback()
    finally:
        db.close()
    return create

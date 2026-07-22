from datetime import date, time
from email.message import EmailMessage

from app import email_config
from app.email_ingest import analizza_email, controlla_posta
from app.models import BozzaEmail, Dipendente, Sede


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _crea_dipendente(db, cognome, nome, sede):
    dip = Dipendente(cognome=cognome, nome=nome, sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def test_analizza_assenza_correttamente_interpretata(db):
    sede = _crea_sede(db)
    dip = _crea_dipendente(db, "Rossi", "Mario", sede)

    corpo = "Nome: Rossi Mario\nTipo: Ferie\nDal: 10/08/2026\nAl: 12/08/2026\nNote: rientro presto\n"
    risultato = analizza_email(db, "ASSENZA", corpo)

    assert risultato["tipo"] == "assenza"
    assert risultato["dipendente_id"] == dip.id
    assert risultato["tipo_assenza"] == "Ferie"
    assert risultato["data_inizio"] == date(2026, 8, 10)
    assert risultato["data_fine"] == date(2026, 8, 12)
    assert risultato["note"] == "rientro presto"
    assert risultato["errore_parsing"] is None


def test_analizza_sostituzione_correttamente_interpretata(db):
    sede = _crea_sede(db)
    assente = _crea_dipendente(db, "Rossi", "Mario", sede)
    sostituto = _crea_dipendente(db, "Verdi", "Luca", sede)

    corpo = "Data: 10/08/2026\nAssente: Rossi Mario\nSostituto: Verdi Luca\nOrario: intera giornata\n"
    risultato = analizza_email(db, "SOSTITUZIONE", corpo)

    assert risultato["tipo"] == "sostituzione"
    assert risultato["dipendente_id"] == assente.id
    assert risultato["dipendente_sostituto_id"] == sostituto.id
    assert risultato["data_inizio"] == date(2026, 8, 10)
    assert risultato["ora_inizio"] is None
    assert risultato["errore_parsing"] is None


def test_analizza_sostituzione_con_orario_parziale(db):
    sede = _crea_sede(db)
    _crea_dipendente(db, "Rossi", "Mario", sede)
    _crea_dipendente(db, "Verdi", "Luca", sede)

    corpo = "Data: 10/08/2026\nAssente: Rossi Mario\nSostituto: Verdi Luca\nOrario: 09:00-13:00\n"
    risultato = analizza_email(db, "SOSTITUZIONE", corpo)

    assert risultato["ora_inizio"] == time(9, 0)
    assert risultato["ora_fine"] == time(13, 0)
    assert risultato["errore_parsing"] is None


def test_analizza_oggetto_non_riconosciuto(db):
    risultato = analizza_email(db, "Ciao, come va?", "testo qualsiasi")
    assert risultato["tipo"] is None


def test_analizza_segnala_dipendente_non_trovato(db):
    _crea_sede(db)
    corpo = "Nome: Pinco Pallino\nTipo: Ferie\nDal: 10/08/2026\nAl: 12/08/2026\n"
    risultato = analizza_email(db, "ASSENZA", corpo)

    assert risultato["dipendente_id"] is None
    assert "non trovato" in risultato["errore_parsing"]


def test_analizza_segnala_omonimia_ambigua(db):
    sede = _crea_sede(db)
    _crea_dipendente(db, "Rossi", "Mario", sede)
    _crea_dipendente(db, "Bianchi", "Mario", sede)  # stesso nome di battesimo, cognome diverso: non ambiguo in realtà
    # Creiamo un vero omonimo esatto per il test di ambiguità.
    dip_a = Dipendente(cognome="Rossi", nome="Mario", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip_a)
    db.commit()

    corpo = "Nome: Rossi Mario\nTipo: Ferie\nDal: 10/08/2026\nAl: 12/08/2026\n"
    risultato = analizza_email(db, "ASSENZA", corpo)

    assert risultato["dipendente_id"] is None
    assert "più dipendenti" in risultato["errore_parsing"]


def test_analizza_segnala_data_mancante_o_non_valida(db):
    sede = _crea_sede(db)
    _crea_dipendente(db, "Rossi", "Mario", sede)
    corpo = "Nome: Rossi Mario\nTipo: Ferie\nDal: non-una-data\nAl: 12/08/2026\n"
    risultato = analizza_email(db, "ASSENZA", corpo)

    assert risultato["data_inizio"] is None
    assert "Dal" in risultato["errore_parsing"]


def _costruisci_email_grezza(mittente: str, oggetto: str, corpo: str) -> bytes:
    messaggio = EmailMessage()
    messaggio["From"] = mittente
    messaggio["Subject"] = oggetto
    messaggio.set_content(corpo)
    return messaggio.as_bytes()


class _FakeImap:
    """Sostituisce imaplib.IMAP4_SSL nei test: nessuna vera connessione,
    restituisce email pre-costruite in memoria."""

    def __init__(self, messaggi: dict[bytes, bytes]):
        self._messaggi = messaggi
        self._contrassegnate = set()

    def login(self, utente, password):
        pass

    def select(self, cartella):
        pass

    def search(self, charset, criterio):
        numeri = b" ".join(n for n in self._messaggi if n not in self._contrassegnate)
        return "OK", [numeri]

    def fetch(self, numero, parti):
        return "OK", [(b"", self._messaggi[numero])]

    def store(self, numero, flag, valore):
        self._contrassegnate.add(numero)

    def close(self):
        pass

    def logout(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _configura_imap_finto(monkeypatch):
    monkeypatch.setattr(email_config, "IMAP_HOST", "imap.esempio.it")
    monkeypatch.setattr(email_config, "IMAP_UTENTE", "turni@esempio.it")
    monkeypatch.setattr(email_config, "IMAP_PASSWORD", "segreta")


def test_controlla_posta_disattivato_senza_configurazione(db, monkeypatch):
    assert controlla_posta() == 0


def test_controlla_posta_crea_bozze_da_email_pertinenti(db, monkeypatch):
    _configura_imap_finto(monkeypatch)
    sede = _crea_sede(db)
    _crea_dipendente(db, "Rossi", "Mario", sede)

    messaggi = {
        b"1": _costruisci_email_grezza(
            "dipendente@esempio.it", "ASSENZA",
            "Nome: Rossi Mario\nTipo: Ferie\nDal: 10/08/2026\nAl: 12/08/2026\n",
        ),
        b"2": _costruisci_email_grezza("altro@esempio.it", "Oggetto qualsiasi", "testo a caso"),
    }
    fake = _FakeImap(messaggi)

    import app.email_ingest as email_ingest
    monkeypatch.setattr(email_ingest.imaplib, "IMAP4_SSL", lambda host, porta: fake)
    monkeypatch.setattr(email_ingest, "SessionLocal", lambda: db)
    # Evita che il "with" chiuda la sessione di test condivisa.
    db.close = lambda: None

    create = controlla_posta()

    assert create == 1
    bozze = db.query(BozzaEmail).all()
    assert len(bozze) == 1
    assert bozze[0].tipo == "assenza"
    assert bozze[0].mittente == "dipendente@esempio.it"
    assert b"1" in fake._contrassegnate
    assert b"2" not in fake._contrassegnate  # email non pertinente: lasciata non letta


def test_se_il_commit_della_bozza_fallisce_lemail_non_viene_segnata_letta(db, monkeypatch):
    """Prima del fix, l'email veniva marcata \\Seen subito dopo db.add(...),
    prima del commit finale: se il commit falliva, l'email spariva (letta)
    senza che nessuna bozza fosse mai salvata davvero, persa per sempre."""
    _configura_imap_finto(monkeypatch)
    sede = _crea_sede(db)
    _crea_dipendente(db, "Rossi", "Mario", sede)

    messaggi = {
        b"1": _costruisci_email_grezza(
            "dipendente@esempio.it", "ASSENZA",
            "Nome: Rossi Mario\nTipo: Ferie\nDal: 10/08/2026\nAl: 12/08/2026\n",
        ),
    }
    fake = _FakeImap(messaggi)

    import app.email_ingest as email_ingest
    monkeypatch.setattr(email_ingest.imaplib, "IMAP4_SSL", lambda host, porta: fake)
    monkeypatch.setattr(email_ingest, "SessionLocal", lambda: db)
    db.close = lambda: None

    def commit_che_fallisce():
        raise RuntimeError("commit fallito (simulato)")

    monkeypatch.setattr(db, "commit", commit_che_fallisce)
    create = controlla_posta()

    assert create == 0
    assert b"1" not in fake._contrassegnate  # deve restare non letta, per essere ritentata

    monkeypatch.undo()
    assert db.query(BozzaEmail).count() == 0  # il rollback ha annullato la bozza parziale

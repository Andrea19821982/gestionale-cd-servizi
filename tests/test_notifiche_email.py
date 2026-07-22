from app.models import Dipendente, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


class _ThreadSincrono:
    """Sostituisce threading.Thread nei test: esegue il target subito,
    nello stesso thread, così l'invio (finto) è già avvenuto quando la
    richiesta HTTP del test restituisce la risposta."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def _configura_smtp_finto(monkeypatch):
    import app.email_config as email_config

    monkeypatch.setattr(email_config, "SMTP_HOST", "smtp.esempio.it")
    monkeypatch.setattr(email_config, "SMTP_UTENTE", "turni@esempio.it")
    monkeypatch.setattr(email_config, "SMTP_PASSWORD", "segreta")
    monkeypatch.setattr(email_config, "DESTINATARI_NOTIFICHE", ["responsabile@esempio.it"])


def test_creazione_assenza_senza_smtp_configurato_non_invia_e_non_rompe(client, crea_utente, db, monkeypatch):
    import app.email_service as email_service

    chiamate = []
    monkeypatch.setattr(email_service, "_invia_ora", lambda oggetto, corpo: chiamate.append(oggetto))

    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="NoSmtp", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert chiamate == []


def test_creazione_assenza_con_smtp_configurato_invia_notifica(client, crea_utente, db, monkeypatch):
    import app.email_service as email_service

    _configura_smtp_finto(monkeypatch)
    monkeypatch.setattr(email_service.threading, "Thread", _ThreadSincrono)
    chiamate = []
    monkeypatch.setattr(email_service, "_invia_ora", lambda oggetto, corpo: chiamate.append((oggetto, corpo)))

    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="ConSmtp", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert len(chiamate) == 1
    oggetto, corpo_html = chiamate[0]
    assert "ConSmtp Test" in oggetto
    assert "ConSmtp Test" in corpo_html
    assert "Ferie" in corpo_html
    assert "2026-08-10" in corpo_html


def test_creazione_sostituzione_con_smtp_configurato_invia_notifica(client, crea_utente, db, monkeypatch):
    import app.email_service as email_service

    _configura_smtp_finto(monkeypatch)
    monkeypatch.setattr(email_service.threading, "Thread", _ThreadSincrono)
    chiamate = []
    monkeypatch.setattr(email_service, "_invia_ora", lambda oggetto, corpo: chiamate.append((oggetto, corpo)))

    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="Partente", nome="Notifica", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="Sostituto", nome="Notifica", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede.id,
            "data": "2026-08-10",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert len(chiamate) == 1
    oggetto, corpo_html = chiamate[0]
    assert "Partente Notifica" in oggetto
    assert "Partente Notifica" in corpo_html
    assert "Sostituto Notifica" in corpo_html
    assert "intera giornata" in corpo_html


def test_invia_ora_non_solleva_eccezione_se_smtp_fallisce(monkeypatch):
    import app.email_config as email_config
    import app.email_service as email_service

    monkeypatch.setattr(email_config, "SMTP_HOST", "smtp.esempio.it")
    monkeypatch.setattr(email_config, "SMTP_UTENTE", "turni@esempio.it")
    monkeypatch.setattr(email_config, "SMTP_PASSWORD", "segreta")
    monkeypatch.setattr(email_config, "DESTINATARI_NOTIFICHE", ["responsabile@esempio.it"])

    class _SmtpCheFallisce:
        def __init__(self, *args, **kwargs):
            raise OSError("connessione rifiutata (simulata)")

    monkeypatch.setattr(email_service.smtplib, "SMTP", _SmtpCheFallisce)

    # Non deve sollevare eccezioni: l'errore va solo registrato nei log.
    email_service._invia_ora("Oggetto di prova", "<p>corpo</p>")

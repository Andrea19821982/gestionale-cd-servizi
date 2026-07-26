from app import email_config, impostazioni_email
from app.models import ImpostazioneImap
from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_imap_test", "passwordsegreta", "amministratore")
    login(client, "admin_imap_test", "passwordsegreta")


def test_imap_effettivo_usa_email_config_se_nessuna_riga_in_db(db, monkeypatch):
    monkeypatch.setattr(email_config, "IMAP_HOST", "imap.file.it")
    monkeypatch.setattr(email_config, "IMAP_UTENTE", "turni@file.it")
    monkeypatch.setattr(email_config, "IMAP_PASSWORD", "segreta-file")

    cfg = impostazioni_email.imap_effettivo(db)

    assert cfg.host == "imap.file.it"
    assert cfg.utente == "turni@file.it"
    assert cfg.password == "segreta-file"


def test_salva_impostazioni_ha_precedenza_su_email_config(db, monkeypatch):
    monkeypatch.setattr(email_config, "IMAP_HOST", "imap.file.it")
    monkeypatch.setattr(email_config, "IMAP_UTENTE", "turni@file.it")
    monkeypatch.setattr(email_config, "IMAP_PASSWORD", "segreta-file")

    impostazioni_email.salva_impostazioni(
        db, utente_id=1, host="imap.db.it", porta=993, utente="turni@db.it",
        password="segreta-db", cartella="INBOX",
    )
    db.commit()  # salva_impostazioni non committa: lo fa il chiamante

    cfg = impostazioni_email.imap_effettivo(db)
    assert cfg.host == "imap.db.it"
    assert cfg.utente == "turni@db.it"
    assert cfg.password == "segreta-db"


def test_salva_impostazioni_con_password_vuota_non_cancella_quella_esistente(db):
    impostazioni_email.salva_impostazioni(
        db, utente_id=1, host="imap.db.it", porta=993, utente="turni@db.it",
        password="segreta-db", cartella="INBOX",
    )
    db.commit()  # salva_impostazioni non committa: lo fa il chiamante

    impostazioni_email.salva_impostazioni(
        db, utente_id=1, host="imap.db.it", porta=993, utente="turni@db.it",
        password="", cartella="INBOX",
    )
    db.commit()

    riga = db.get(ImpostazioneImap, 1)
    assert riga.password == "segreta-db"


def test_pagina_bozze_email_mostra_form_configurazione_imap_solo_amministratore(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.get("/bozze-email")
    assert r.status_code == 200
    assert "Casella email per le richieste dei dipendenti" in r.text


def test_imposta_imap_richiede_amministratore(client, crea_utente):
    crea_utente("gestore_imap_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_imap_test", "passwordsegreta")

    r = client.post(
        "/bozze-email/imposta-imap",
        data={"host": "imap.hack.it", "porta": "993", "imap_utente": "x@x.it", "password": "x", "cartella": "INBOX"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_imposta_imap_salva_e_si_riflette_nella_pagina(client, crea_utente, db):
    _login_admin(client, crea_utente)

    r = client.post(
        "/bozze-email/imposta-imap",
        data={
            "host": "imap.nuovo.it", "porta": "993", "imap_utente": "turni@nuovo.it",
            "password": "nuovapassword", "cartella": "INBOX",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.get("/bozze-email")
    assert "turni@nuovo.it" in r.text
    assert "nuovapassword" not in r.text  # la password non va mai mostrata


def test_guida_email_stampa_contiene_bozza_e_istruzioni(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.get("/bozze-email/guida-stampa")
    assert r.status_code == 200
    assert "COME SEGNALARE UN" in r.text and "ASSENZA" in r.text
    assert "COME SEGNALARE UNA SOSTITUZIONE" in r.text

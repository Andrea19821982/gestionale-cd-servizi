from datetime import date, timedelta

import app.allarme_copertura as allarme_copertura
from app import email_config
from app.models import AllarmeCoperturaInviato, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test", copertura_minima_ordinaria=0):
    # Il nome del parametro resta quello storico per non dover toccare ogni
    # chiamata nei test sotto: applica lo stesso minimo a entrambe le fasce
    # (vedi Sede.copertura_minima_mattina/pomeriggio), che per questi test
    # generici basta e avanza — non gli interessa la distinzione tra fasce.
    sede = Sede(
        nome=nome, colore_hex="#123456", attivo=True,
        copertura_minima_mattina=copertura_minima_ordinaria,
        copertura_minima_pomeriggio=copertura_minima_ordinaria,
    )
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _configura_allarme(monkeypatch):
    monkeypatch.setattr(email_config, "SMTP_HOST", "smtp.esempio.it")
    monkeypatch.setattr(email_config, "SMTP_UTENTE", "turni@esempio.it")
    monkeypatch.setattr(email_config, "SMTP_PASSWORD", "segreta")
    monkeypatch.setattr(email_config, "ALLARME_COPERTURA_DESTINATARI", ["gestore@esempio.it"])
    monkeypatch.setattr(email_config, "ALLARME_COPERTURA_ABILITATO", True)


def _invio_finto_riuscito(monkeypatch, chiamate=None):
    def _finto(oggetto, corpo_html, destinatari=None):
        if chiamate is not None:
            chiamate.append((oggetto, corpo_html, destinatari))
        return True

    monkeypatch.setattr(allarme_copertura, "_invia_ora", _finto)


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_non_configurato_non_segnala_nulla(db):
    _crea_sede(db, copertura_minima_ordinaria=5)
    assert allarme_copertura.controlla_e_segnala_carenza(db) is False
    assert db.query(AllarmeCoperturaInviato).count() == 0


def test_nessuna_carenza_non_invia_nulla(db, monkeypatch):
    _configura_allarme(monkeypatch)
    _invio_finto_riuscito(monkeypatch)
    _crea_sede(db)  # copertura_minima_ordinaria=0 -> mai sotto il minimo

    assert allarme_copertura.controlla_e_segnala_carenza(db) is False
    assert db.query(AllarmeCoperturaInviato).count() == 0


def test_carenza_segnalata_e_registrata(db, monkeypatch):
    _configura_allarme(monkeypatch)
    chiamate = []
    _invio_finto_riuscito(monkeypatch, chiamate)
    sede = _crea_sede(db, copertura_minima_ordinaria=3)

    riuscito = allarme_copertura.controlla_e_segnala_carenza(db)

    assert riuscito is True
    assert len(chiamate) == 1
    oggetto, corpo_html, destinatari = chiamate[0]
    assert sede.nome in oggetto
    assert sede.nome in corpo_html
    assert destinatari == ["gestore@esempio.it"]

    domani = date.today() + timedelta(days=1)
    riga = db.query(AllarmeCoperturaInviato).filter_by(data_riferimento=domani).first()
    assert riga is not None
    assert riga.manuale is False
    assert sede.nome in riga.palazzi_carenti


def test_non_segnala_due_volte_lo_stesso_giorno(db, monkeypatch):
    _configura_allarme(monkeypatch)
    _invio_finto_riuscito(monkeypatch)
    _crea_sede(db, copertura_minima_ordinaria=3)

    assert allarme_copertura.controlla_e_segnala_carenza(db) is True
    assert allarme_copertura.controlla_e_segnala_carenza(db) is False
    assert db.query(AllarmeCoperturaInviato).count() == 1


def test_forza_permette_il_reinvio_senza_duplicare_la_riga(db, monkeypatch):
    _configura_allarme(monkeypatch)
    _invio_finto_riuscito(monkeypatch)
    _crea_sede(db, copertura_minima_ordinaria=3)

    allarme_copertura.controlla_e_segnala_carenza(db)
    riuscito = allarme_copertura.controlla_e_segnala_carenza(db, forza=True, inviato_da=None)

    assert riuscito is True
    domani = date.today() + timedelta(days=1)
    righe = db.query(AllarmeCoperturaInviato).filter_by(data_riferimento=domani).all()
    assert len(righe) == 1
    assert righe[0].manuale is True


def test_pulsante_invia_ora_via_http(client, crea_utente, db, monkeypatch):
    _configura_allarme(monkeypatch)
    _invio_finto_riuscito(monkeypatch)
    _crea_sede(db, copertura_minima_ordinaria=3)
    _login_admin(client, crea_utente)

    r = client.post("/allarme-copertura/invia-ora", follow_redirects=True)

    assert r.status_code == 200
    domani = date.today() + timedelta(days=1)
    riga = db.query(AllarmeCoperturaInviato).filter_by(data_riferimento=domani).first()
    assert riga is not None
    assert riga.manuale is True


def test_pagina_richiede_ruolo_operativo(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/allarme-copertura", follow_redirects=False)
    assert r.status_code == 403
    r2 = client.post("/allarme-copertura/invia-ora", follow_redirects=False)
    assert r2.status_code == 403


def test_invii_concorrenti_non_devono_far_esplodere_un_errore_del_database(db, monkeypatch, SessionTest):
    """Stessa race di riepilogo_giornaliero.py (vedi test analogo lì): il
    controllo "già segnalato oggi?" e l'insert/update finale non sono
    atomici. Due chiamate concorrenti (due sessioni indipendenti) che
    leggono entrambe gia_inviato=None prima che una delle due scriva la
    propria riga finiscono per scontrarsi sull'UniqueConstraint su
    data_riferimento al secondo commit: prima del fix quell'IntegrityError
    non era gestito e saliva al chiamante."""
    _configura_allarme(monkeypatch)
    _crea_sede(db, copertura_minima_ordinaria=3)
    chiamate = []

    def _finto_con_richiesta_concorrente(oggetto, corpo_html, destinatari=None):
        chiamate.append((oggetto, corpo_html, destinatari))
        if len(chiamate) == 1:
            db_concorrente = SessionTest()
            try:
                assert allarme_copertura.controlla_e_segnala_carenza(db_concorrente, forza=True) is True
            finally:
                db_concorrente.close()
        return True

    monkeypatch.setattr(allarme_copertura, "_invia_ora", _finto_con_richiesta_concorrente)

    assert allarme_copertura.controlla_e_segnala_carenza(db, forza=True) is True

    domani = date.today() + timedelta(days=1)
    assert db.query(AllarmeCoperturaInviato).filter_by(data_riferimento=domani).count() == 1


def test_controlla_e_invia_se_dovuto_rispetta_orario_configurato(db, monkeypatch):
    _configura_allarme(monkeypatch)
    _invio_finto_riuscito(monkeypatch)
    _crea_sede(db, copertura_minima_ordinaria=3)
    monkeypatch.setattr(allarme_copertura, "SessionLocal", lambda: db)
    db.close = lambda: None
    monkeypatch.setattr(email_config, "ALLARME_COPERTURA_ORA", "23:59")

    assert allarme_copertura.controlla_e_invia_se_dovuto() is False
    assert db.query(AllarmeCoperturaInviato).count() == 0


def _login_gestore(client, crea_utente):
    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")


def test_destinatari_da_interfaccia_hanno_precedenza_sul_file(db, monkeypatch):
    from app import impostazioni_allarme_copertura

    monkeypatch.setattr(email_config, "ALLARME_COPERTURA_DESTINATARI", ["file@esempio.it"])
    impostazioni_allarme_copertura.salva_destinatari(db, 1, "uno@esempio.it", "due@esempio.it", "")

    assert impostazioni_allarme_copertura.destinatari_effettivi(db) == ["uno@esempio.it", "due@esempio.it"]


def test_destinatari_ricade_sul_file_se_i_tre_campi_sono_vuoti(db, monkeypatch):
    from app import impostazioni_allarme_copertura

    monkeypatch.setattr(email_config, "ALLARME_COPERTURA_DESTINATARI", ["file@esempio.it"])
    impostazioni_allarme_copertura.salva_destinatari(db, 1, "", "", "")

    assert impostazioni_allarme_copertura.destinatari_effettivi(db) == ["file@esempio.it"]


def test_imposta_destinatari_via_http_solo_amministratore(client, crea_utente, db):
    _login_gestore(client, crea_utente)
    r = client.post(
        "/allarme-copertura/destinatari",
        data={"email_1": "a@esempio.it", "email_2": "", "email_3": ""},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_imposta_destinatari_via_http_salva_e_si_riflette_nella_pagina(client, crea_utente, db):
    _login_admin(client, crea_utente)
    r = client.post(
        "/allarme-copertura/destinatari",
        data={"email_1": "primo@esempio.it", "email_2": "secondo@esempio.it", "email_3": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303

    r2 = client.get("/allarme-copertura")
    assert "primo@esempio.it" in r2.text
    assert "secondo@esempio.it" in r2.text


def test_pagina_allarme_copertura_sezione_destinatari_solo_amministratore(client, crea_utente, db):
    _login_gestore(client, crea_utente)
    r = client.get("/allarme-copertura")
    assert r.status_code == 200
    assert "Destinatari dell'allarme" not in r.text


def test_banner_carenza_compare_per_gestore_e_ammin_non_per_consultazione(client, crea_utente, db):
    _crea_sede(db, copertura_minima_ordinaria=3)

    crea_utente("consultazione_carenza", "passwordsegreta", "consultazione")
    login(client, "consultazione_carenza", "passwordsegreta")
    r = client.get("/calendario")
    assert "Copertura sotto il minimo" not in r.text

    _login_gestore(client, crea_utente)
    r2 = client.get("/calendario")
    assert "Copertura sotto il minimo domani" in r2.text


def test_banner_carenza_assente_se_copertura_sufficiente(client, crea_utente, db):
    _crea_sede(db, copertura_minima_ordinaria=0)
    _login_admin(client, crea_utente)
    r = client.get("/calendario")
    assert "Copertura sotto il minimo" not in r.text

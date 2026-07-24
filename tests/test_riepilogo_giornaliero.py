from datetime import date, time, timedelta

import pytest

import app.riepilogo_giornaliero as riepilogo_giornaliero
from app import email_config
from app.models import AssegnazioneGiornaliera, Dipendente, EventoSala, InvioGiornaliero, Sala, Sede, TipoTurno
from tests.conftest import login


def _crea_sede(db, nome="Sede Test", copertura_minima_ordinaria=0):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True, copertura_minima_ordinaria=copertura_minima_ordinaria)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _configura_riepilogo(monkeypatch):
    monkeypatch.setattr(email_config, "SMTP_HOST", "smtp.esempio.it")
    monkeypatch.setattr(email_config, "SMTP_UTENTE", "turni@esempio.it")
    monkeypatch.setattr(email_config, "SMTP_PASSWORD", "segreta")
    monkeypatch.setattr(email_config, "RIEPILOGO_GIORNALIERO_DESTINATARI", ["referente@camera.it"])
    monkeypatch.setattr(email_config, "RIEPILOGO_GIORNALIERO_ABILITATO", True)


def _invio_finto_riuscito(monkeypatch, chiamate=None):
    def _finto(oggetto, corpo_html, destinatari=None):
        if chiamate is not None:
            chiamate.append((oggetto, corpo_html, destinatari))
        return True

    monkeypatch.setattr(riepilogo_giornaliero, "_invia_ora", _finto)


def _login_admin(client, crea_utente):
    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    return admin


def test_non_configurato_non_invia_nulla(db):
    assert riepilogo_giornaliero.invia_riepilogo_giornaliero(db) is False
    assert db.query(InvioGiornaliero).count() == 0


def test_contenuto_corretto_e_invio_registrato(db, monkeypatch):
    _configura_riepilogo(monkeypatch)
    chiamate = []
    _invio_finto_riuscito(monkeypatch, chiamate)

    sede = _crea_sede(db)
    tipo = TipoTurno(etichetta="Mattina Rip", ora_inizio=time(7, 0), ora_fine=time(13, 30))
    db.add(tipo)
    db.commit()
    dip = Dipendente(cognome="Rossi", nome="Mario", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    domani = date.today() + timedelta(days=1)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=domani, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    riuscito = riepilogo_giornaliero.invia_riepilogo_giornaliero(db)

    assert riuscito is True
    assert len(chiamate) == 1
    oggetto, corpo_html, destinatari = chiamate[0]
    assert domani.strftime("%d/%m/%Y") in oggetto
    assert "Rossi Mario" in corpo_html
    assert destinatari == ["referente@camera.it"]

    riga = db.query(InvioGiornaliero).filter_by(data_riepilogo=domani).first()
    assert riga is not None
    assert riga.manuale is False


def test_non_invia_due_volte_lo_stesso_giorno(db, monkeypatch):
    _configura_riepilogo(monkeypatch)
    _invio_finto_riuscito(monkeypatch)

    assert riepilogo_giornaliero.invia_riepilogo_giornaliero(db) is True
    assert riepilogo_giornaliero.invia_riepilogo_giornaliero(db) is False

    domani = date.today() + timedelta(days=1)
    assert db.query(InvioGiornaliero).filter_by(data_riepilogo=domani).count() == 1


def test_forza_permette_il_reinvio_senza_duplicare_la_riga(db, monkeypatch):
    _configura_riepilogo(monkeypatch)
    _invio_finto_riuscito(monkeypatch)

    riepilogo_giornaliero.invia_riepilogo_giornaliero(db)
    riuscito = riepilogo_giornaliero.invia_riepilogo_giornaliero(db, forza=True, inviato_da=None)

    assert riuscito is True
    domani = date.today() + timedelta(days=1)
    righe = db.query(InvioGiornaliero).filter_by(data_riepilogo=domani).all()
    assert len(righe) == 1
    assert righe[0].manuale is True


def test_pulsante_invia_ora_via_http(client, crea_utente, db, monkeypatch):
    _configura_riepilogo(monkeypatch)
    _invio_finto_riuscito(monkeypatch)
    _login_admin(client, crea_utente)

    r = client.post("/riepilogo-giornaliero/invia-ora", follow_redirects=True)

    assert r.status_code == 200
    domani = date.today() + timedelta(days=1)
    riga = db.query(InvioGiornaliero).filter_by(data_riepilogo=domani).first()
    assert riga is not None
    assert riga.manuale is True


def test_pagina_richiede_ruolo_operativo(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/riepilogo-giornaliero", follow_redirects=False)
    assert r.status_code == 403
    r2 = client.post("/riepilogo-giornaliero/invia-ora", follow_redirects=False)
    assert r2.status_code == 403


def test_email_segnala_copertura_sotto_il_minimo(db, monkeypatch):
    _configura_riepilogo(monkeypatch)
    chiamate = []
    _invio_finto_riuscito(monkeypatch, chiamate)

    sede = _crea_sede(db, copertura_minima_ordinaria=2)
    sala = Sala(nome="Sala della Lupa Rip", sede_id=sede.id, copertura_minima_aggiuntiva=1, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    domani = date.today() + timedelta(days=1)
    db.add(EventoSala(sala_id=sala.id, data_inizio=domani, data_fine=domani, descrizione="Seduta Rip"))
    db.commit()

    assert riepilogo_giornaliero.invia_riepilogo_giornaliero(db) is True
    _, corpo_html, _ = chiamate[0]
    assert "Sotto il minimo richiesto" in corpo_html
    assert "Sala della Lupa Rip" in corpo_html


def test_invii_concorrenti_non_devono_far_esplodere_un_errore_del_database(db, monkeypatch, SessionTest):
    """Il guard "già inviato oggi?" (query poi, molto più tardi, insert) non
    è atomico: se due chiamate concorrenti (due sessioni, come sarebbero due
    richieste HTTP, o il thread di sfondo e un "Invia ora" quasi in
    contemporanea) leggono entrambe gia_inviato=None prima che una delle due
    abbia scritto la sua riga, entrambe spediscono la mail (doppio invio) e
    la seconda a committare si scontra con l'UniqueConstraint su
    data_riepilogo: prima del fix, quell'IntegrityError non era gestito e
    saliva fino al chiamante (un 500 per l'utente che ha premuto il
    pulsante, con la mail già spedita comunque). Si simula la sovrapposizione
    facendo scattare la "seconda richiesta" (sessione indipendente,
    stesso database) dentro il finto invio della prima, cioè esattamente nel
    punto in cui la prima ha già superato il controllo ma non ha ancora
    scritto la propria riga."""
    _configura_riepilogo(monkeypatch)
    chiamate = []

    def _finto_con_richiesta_concorrente(oggetto, corpo_html, destinatari=None):
        chiamate.append((oggetto, corpo_html, destinatari))
        if len(chiamate) == 1:
            db_concorrente = SessionTest()
            try:
                assert riepilogo_giornaliero.invia_riepilogo_giornaliero(db_concorrente, forza=True) is True
            finally:
                db_concorrente.close()
        return True

    monkeypatch.setattr(riepilogo_giornaliero, "_invia_ora", _finto_con_richiesta_concorrente)

    # Non deve sollevare IntegrityError: la seconda scrittura in conflitto va
    # gestita (rollback e via), non propagata.
    assert riepilogo_giornaliero.invia_riepilogo_giornaliero(db, forza=True) is True

    domani = date.today() + timedelta(days=1)
    # Una sola riga per la data, anche se la mail è stata spedita due volte.
    assert db.query(InvioGiornaliero).filter_by(data_riepilogo=domani).count() == 1


def test_controlla_e_invia_se_dovuto_rispetta_orario_configurato(db, monkeypatch):
    _configura_riepilogo(monkeypatch)
    _invio_finto_riuscito(monkeypatch)
    monkeypatch.setattr(riepilogo_giornaliero, "SessionLocal", lambda: db)
    db.close = lambda: None
    # Un orario impossibile da raggiungere oggi (23:59) impedisce l'invio
    # automatico anche se tutto il resto è configurato.
    monkeypatch.setattr(email_config, "RIEPILOGO_GIORNALIERO_ORA", "23:59")

    assert riepilogo_giornaliero.controlla_e_invia_se_dovuto() is False
    assert db.query(InvioGiornaliero).count() == 0

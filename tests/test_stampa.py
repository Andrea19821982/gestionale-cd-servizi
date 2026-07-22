from datetime import date

from app.models import AssegnazioneGiornaliera, Dipendente, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test", colore="#123456"):
    sede = Sede(nome=nome, colore_hex=colore, attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_stampa_singola_sede_mostra_dati_e_niente_select(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Stampa Singola")
    dip = Dipendente(cognome="Stampa", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()

    r = client.get(f"/calendario/stampa?sede_id={sede.id}&anno=2026&mese=8")
    assert r.status_code == 200
    assert "Sede Stampa Singola" in r.text
    assert "Stampa Test" in r.text
    assert "<select" not in r.text


def test_stampa_tutte_le_sedi_una_pagina_ciascuna(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede_a = _crea_sede(db, "Sede Stampa A")
    sede_b = _crea_sede(db, "Sede Stampa B")

    r = client.get("/calendario/stampa?tutte=1&anno=2026&mese=8")
    assert r.status_code == 200
    assert "Sede Stampa A" in r.text
    assert "Sede Stampa B" in r.text
    assert r.text.count('class="pagina-stampa"') == 2


def test_stampa_sede_inesistente_non_crasha(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.get("/calendario/stampa?sede_id=9999&anno=2026&mese=8")
    assert r.status_code == 200
    assert "Nessuna sede da stampare." in r.text


def test_stampa_mostra_assenza(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Stampa Assenza")
    dip = Dipendente(cognome="ConAssenza", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-10", "tipo_assenza": "Ferie"},
    )

    r = client.get(f"/calendario/stampa?sede_id={sede.id}&anno=2026&mese=8")
    assert r.status_code == 200
    assert "ASSENTE" in r.text


def test_stampa_richiede_login(client):
    r = client.get("/calendario/stampa", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_stampa_accessibile_a_consultazione(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db, "Sede Stampa Consultazione")

    r = client.get(f"/calendario/stampa?sede_id={sede.id}&anno=2026&mese=8")
    assert r.status_code == 200

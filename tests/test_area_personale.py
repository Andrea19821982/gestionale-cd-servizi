from datetime import date, time

from app.auth import hash_password
from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Sede, TipoTurno, Utente
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _crea_dipendente_con_login(db, sede, username="dip_test", password="passwordsegreta"):
    dip = Dipendente(cognome="Personale", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    utente = Utente(
        username=username,
        password_hash=hash_password(password),
        ruolo="dipendente",
        dipendente_collegato_id=dip.id,
        attivo=True,
    )
    db.add(utente)
    db.commit()
    db.refresh(utente)
    return dip, utente


def test_dipendente_vede_la_propria_area_personale(client, db):
    sede = _crea_sede(db)
    dip, _ = _crea_dipendente_con_login(db, sede)
    login(client, "dip_test", "passwordsegreta")

    r = client.get("/area-personale")
    assert r.status_code == 200
    assert "Personale Test" in r.text


def test_dipendente_vede_solo_il_proprio_calendario_e_ferie(client, db):
    sede = _crea_sede(db)
    tipo = TipoTurno(etichetta="Mattina AP", ora_inizio=time(7, 0), ora_fine=time(13, 30))
    db.add(tipo)
    db.commit()
    db.refresh(tipo)

    dip, _ = _crea_dipendente_con_login(db, sede)
    altro = Dipendente(cognome="Altro", nome="Collega", sede_riferimento_id=sede.id, attivo=True)
    db.add(altro)
    db.commit()
    db.refresh(altro)

    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 8, 10), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.add(AssegnazioneGiornaliera(
        dipendente_id=altro.id, data=date(2026, 8, 10), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    login(client, "dip_test", "passwordsegreta")
    r = client.get("/area-personale?anno=2026&mese=8")
    assert r.status_code == 200
    assert "Mattina AP" in r.text
    assert "Altro Collega" not in r.text


def test_dipendente_non_puo_accedere_alle_altre_pagine(client, db):
    sede = _crea_sede(db)
    _crea_dipendente_con_login(db, sede)
    login(client, "dip_test", "passwordsegreta")

    assert client.get("/calendario", follow_redirects=False).status_code == 403
    assert client.get("/dipendenti", follow_redirects=False).status_code == 403
    assert client.get("/assenze", follow_redirects=False).status_code == 403
    assert client.get("/statistiche", follow_redirects=False).status_code == 403
    assert client.get("/utenti", follow_redirects=False).status_code == 403


def test_utente_dipendente_senza_collegamento_riceve_errore_chiaro(client, crea_utente):
    crea_utente("dip_senza_link", "passwordsegreta", "dipendente")
    login(client, "dip_senza_link", "passwordsegreta")

    r = client.get("/area-personale", follow_redirects=False)
    assert r.status_code == 400


def test_area_personale_richiede_login(client):
    r = client.get("/area-personale", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")

from app.models import Sede, SottosezioneCopertura
from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_sedi_test", "passwordsegreta", "amministratore")
    login(client, "admin_sedi_test", "passwordsegreta")


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def test_crea_sede_con_minimi_mattina_pomeriggio(client, crea_utente, db):
    _login_admin(client, crea_utente)
    r = client.post(
        "/sedi/nuova",
        data={
            "nome": "Sede Fasce Test", "colore_hex": "#2563eb",
            "copertura_minima_mattina": "3", "copertura_minima_pomeriggio": "2",
            "ordine_visualizzazione": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    sede = db.query(Sede).filter_by(nome="Sede Fasce Test").first()
    assert sede.copertura_minima_mattina == 3
    assert sede.copertura_minima_pomeriggio == 2


def test_modifica_sede_aggiorna_minimi_mattina_pomeriggio(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)

    r = client.post(
        f"/sedi/{sede.id}/modifica",
        data={
            "nome": sede.nome, "colore_hex": sede.colore_hex,
            "copertura_minima_mattina": "5", "copertura_minima_pomeriggio": "1",
            "ordine_visualizzazione": "0", "attivo": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.refresh(sede)
    assert sede.copertura_minima_mattina == 5
    assert sede.copertura_minima_pomeriggio == 1


def test_crea_sede_con_minimo_negativo_da_400(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/sedi/nuova",
        data={
            "nome": "Sede Negativa", "colore_hex": "#2563eb",
            "copertura_minima_mattina": "-1", "copertura_minima_pomeriggio": "0",
            "ordine_visualizzazione": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_crea_comparto_copertura(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Con Comparto")

    r = client.post(
        "/sedi/comparti/nuovo",
        data={
            "sede_id": sede.id, "nome": "Parcheggio",
            "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    comparto = db.query(SottosezioneCopertura).filter_by(sede_id=sede.id, nome="Parcheggio").first()
    assert comparto is not None
    assert comparto.copertura_minima_mattina == 1
    assert comparto.copertura_minima_pomeriggio == 1


def test_modifica_comparto_copertura(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Con Comparto Da Modificare")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Archivio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    db.commit()
    db.refresh(comparto)

    r = client.post(
        f"/sedi/comparti/{comparto.id}/modifica",
        data={
            "sede_id": sede.id, "nome": "Archivio legislativo",
            "copertura_minima_mattina": "2", "copertura_minima_pomeriggio": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.refresh(comparto)
    assert comparto.nome == "Archivio legislativo"
    assert comparto.copertura_minima_mattina == 2


def test_pagina_sedi_mostra_comparti_esistenti(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Con Comparto Visibile")
    db.add(SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1))
    db.commit()

    r = client.get("/sedi")
    assert r.status_code == 200
    assert "Parcheggio" in r.text


def test_comparti_richiede_amministratore_per_creare(client, crea_utente, db):
    crea_utente("gestore_sedi_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_sedi_test", "passwordsegreta")
    sede = _crea_sede(db, "Sede Gestore Test")

    r = client.post(
        "/sedi/comparti/nuovo",
        data={"sede_id": sede.id, "nome": "Parcheggio", "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 403

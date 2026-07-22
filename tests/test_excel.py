from io import BytesIO

from openpyxl import load_workbook

from app.models import Dipendente, Sede
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


def test_excel_singola_sede(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Excel Singola")
    dip = Dipendente(cognome="Excel", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()

    r = client.get(f"/calendario/excel?sede_id={sede.id}&anno=2026&mese=8")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    cartella = load_workbook(BytesIO(r.content))
    assert cartella.sheetnames == ["Sede Excel Singola"]
    foglio = cartella["Sede Excel Singola"]
    assert foglio.cell(row=1, column=1).value == "Dipendente"
    assert foglio.cell(row=2, column=1).value == "Excel Test"


def test_excel_tutte_le_sedi(client, crea_utente, db):
    _login_admin(client, crea_utente)
    _crea_sede(db, "Excel Sede A")
    _crea_sede(db, "Excel Sede B")

    r = client.get("/calendario/excel?tutte=1&anno=2026&mese=8")
    assert r.status_code == 200
    cartella = load_workbook(BytesIO(r.content))
    assert "Excel Sede A" in cartella.sheetnames
    assert "Excel Sede B" in cartella.sheetnames


def test_excel_sede_inesistente_non_crasha(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.get("/calendario/excel?sede_id=9999&anno=2026&mese=8")
    assert r.status_code == 200
    cartella = load_workbook(BytesIO(r.content))
    assert cartella.sheetnames == ["Nessuna sede"]


def test_excel_richiede_login(client):
    r = client.get("/calendario/excel", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_excel_accessibile_a_consultazione(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db, "Sede Excel Consultazione")

    r = client.get(f"/calendario/excel?sede_id={sede.id}&anno=2026&mese=8")
    assert r.status_code == 200

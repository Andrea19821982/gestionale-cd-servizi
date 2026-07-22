from app.models import Assenza, Dipendente, Sede
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


def test_allegato_valido_viene_salvato_e_scaricabile(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Allegato", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        files={"allegato": ("certificato.pdf", b"%PDF-1.4 contenuto finto", "application/pdf")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    assert assenza.allegato_nome == "certificato.pdf"
    assert assenza.allegato_path is not None

    r2 = client.get(f"/assenze/{assenza.id}/allegato")
    assert r2.status_code == 200
    assert r2.content == b"%PDF-1.4 contenuto finto"


def test_allegato_con_estensione_non_ammessa_viene_rifiutato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="EstensioneErrata", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        files={"allegato": ("virus.exe", b"contenuto", "application/octet-stream")},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert db.query(Assenza).filter_by(dipendente_id=dip.id).first() is None


def test_allegato_troppo_grande_viene_rifiutato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="FileGrande", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    contenuto_grande = b"0" * (5 * 1024 * 1024 + 1)
    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        files={"allegato": ("certificato.pdf", contenuto_grande, "application/pdf")},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_assenza_senza_allegato_non_ha_link_di_download(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="SenzaAllegato", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    r = client.get(f"/assenze/{assenza.id}/allegato")
    assert r.status_code == 404

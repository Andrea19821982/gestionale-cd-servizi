from datetime import date, timedelta

from app.models import Assenza, Dipendente, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    return crea_utente("admin_test", "passwordsegreta", "amministratore")


def test_delegato_puo_approvare_solo_nel_periodo_delegato(client, crea_utente, db):
    admin = _login_admin(client, crea_utente)
    login(client, "admin_test", "passwordsegreta")
    gestore = crea_utente("gestore_delegato", "passwordsegreta", "gestore_turni")

    oggi = date.today()
    client.post(
        "/deleghe/nuova",
        data={
            "utente_delegato_id": gestore.id,
            "data_inizio": (oggi - timedelta(days=1)).isoformat(),
            "data_fine": (oggi + timedelta(days=1)).isoformat(),
        },
    )

    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Delega", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(Assenza(dipendente_id=dip.id, data_inizio=oggi, data_fine=oggi, tipo_assenza="Ferie"))
    db.commit()
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    login(client, "gestore_delegato", "passwordsegreta")
    r = client.post(f"/assenze/{assenza.id}/approva", follow_redirects=False)
    assert r.status_code == 303


def test_gestore_senza_delega_non_puo_approvare(client, crea_utente, db):
    crea_utente("gestore_semplice", "passwordsegreta", "gestore_turni")
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="SenzaDelega", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(Assenza(dipendente_id=dip.id, data_inizio=date.today(), data_fine=date.today(), tipo_assenza="Ferie"))
    db.commit()
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    login(client, "gestore_semplice", "passwordsegreta")
    r = client.post(f"/assenze/{assenza.id}/approva", follow_redirects=False)
    assert r.status_code == 403


def test_delega_scaduta_non_da_piu_diritto_di_approvare(client, crea_utente, db):
    _login_admin(client, crea_utente)
    login(client, "admin_test", "passwordsegreta")
    gestore = crea_utente("gestore_scaduto", "passwordsegreta", "gestore_turni")

    oggi = date.today()
    client.post(
        "/deleghe/nuova",
        data={
            "utente_delegato_id": gestore.id,
            "data_inizio": (oggi - timedelta(days=10)).isoformat(),
            "data_fine": (oggi - timedelta(days=5)).isoformat(),
        },
    )

    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="DelegaScaduta", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(Assenza(dipendente_id=dip.id, data_inizio=oggi, data_fine=oggi, tipo_assenza="Ferie"))
    db.commit()
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    login(client, "gestore_scaduto", "passwordsegreta")
    r = client.post(f"/assenze/{assenza.id}/approva", follow_redirects=False)
    assert r.status_code == 403


def test_non_si_puo_delegare_un_account_dipendente(client, crea_utente, db):
    _login_admin(client, crea_utente)
    login(client, "admin_test", "passwordsegreta")
    dipendente_utente = crea_utente("account_dipendente", "passwordsegreta", "dipendente")

    oggi = date.today()
    r = client.post(
        "/deleghe/nuova",
        data={
            "utente_delegato_id": dipendente_utente.id,
            "data_inizio": oggi.isoformat(),
            "data_fine": oggi.isoformat(),
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_solo_amministratore_gestisce_utenti_e_deleghe(client, crea_utente):
    crea_utente("gestore_qualsiasi", "passwordsegreta", "gestore_turni")
    login(client, "gestore_qualsiasi", "passwordsegreta")

    assert client.get("/utenti", follow_redirects=False).status_code == 403
    assert client.post(
        "/utenti/nuovo",
        data={"username": "x", "password": "passwordsegreta", "ruolo": "consultazione"},
        follow_redirects=False,
    ).status_code == 403

from datetime import date

from app.models import Assenza, Dipendente, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def test_banner_visibile_per_amministratore_con_richieste_pendenti(client, crea_utente, db):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Banner", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(Assenza(dipendente_id=dip.id, data_inizio=date.today(), data_fine=date.today(), tipo_assenza="Ferie"))
    db.commit()

    login(client, "admin_test", "passwordsegreta")
    r = client.get("/calendario")
    assert "in attesa di approvazione" in r.text


def test_banner_assente_senza_richieste_pendenti(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    r = client.get("/calendario")
    assert "in attesa di approvazione" not in r.text


def test_banner_non_visibile_a_chi_non_puo_approvare(client, crea_utente, db):
    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="BannerGestore", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(Assenza(dipendente_id=dip.id, data_inizio=date.today(), data_fine=date.today(), tipo_assenza="Ferie"))
    db.commit()

    login(client, "gestore_test", "passwordsegreta")
    r = client.get("/calendario")
    assert "in attesa di approvazione" not in r.text

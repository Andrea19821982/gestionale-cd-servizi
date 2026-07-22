from calendar import monthrange
from datetime import date

from app.models import Dipendente, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test", colore="#123456"):
    sede = Sede(nome=nome, colore_hex=colore, attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def test_numero_colonne_giorno_corretto_per_mese(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    db.add(Dipendente(cognome="Test", nome="Uno", sede_riferimento_id=sede.id, attivo=True))
    db.commit()

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=2")
    assert r.status_code == 200
    giorni_febbraio_2026 = monthrange(2026, 2)[1]
    assert giorni_febbraio_2026 == 28
    # un'intestazione con l'iniziale del giorno per ciascun giorno del mese
    assert r.text.count('<span class="muted">') == 28


def test_weekend_evidenziati_correttamente(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    db.add(Dipendente(cognome="Test", nome="Uno", sede_riferimento_id=sede.id, attivo=True))
    db.commit()

    anno, mese = 2026, 7
    numero_giorni = monthrange(anno, mese)[1]
    weekend_attesi = sum(
        1 for g in range(1, numero_giorni + 1) if date(anno, mese, g).weekday() >= 5
    )

    r = client.get(f"/calendario?sede_id={sede.id}&anno={anno}&mese={mese}")
    assert r.status_code == 200
    # ogni giorno di weekend produce sia un <th class="weekend"> che un <td class="weekend">
    assert r.text.count('class="weekend"') == weekend_attesi * 2


def test_dipendenti_filtrati_per_sede(client, crea_utente, db):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    sede_a = _crea_sede(db, "Sede A", "#111111")
    sede_b = _crea_sede(db, "Sede B", "#222222")
    db.add(Dipendente(cognome="DellaSedeA", nome="Test", sede_riferimento_id=sede_a.id, attivo=True))
    db.add(Dipendente(cognome="DellaSedeB", nome="Test", sede_riferimento_id=sede_b.id, attivo=True))
    db.commit()

    r = client.get(f"/calendario?sede_id={sede_a.id}&anno=2026&mese=7")
    assert "DellaSedeA" in r.text
    assert "DellaSedeB" not in r.text


def test_consultazione_puo_vedere_calendario(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=7")
    assert r.status_code == 200


def test_calendario_richiede_login(client):
    r = client.get("/calendario", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")

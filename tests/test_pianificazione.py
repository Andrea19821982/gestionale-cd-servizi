from calendar import monthrange
from datetime import date, time

from app.models import AssegnazioneGiornaliera, Dipendente, PatternTurno, Sede, TipoTurno
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _crea_tipi_turno(db):
    mattina = TipoTurno(etichetta="Mattina Test", ora_inizio=time(7, 0), ora_fine=time(13, 30))
    pomeriggio = TipoTurno(etichetta="Pomeriggio Test", ora_inizio=time(13, 30), ora_fine=time(20, 0))
    db.add_all([mattina, pomeriggio])
    db.commit()
    db.refresh(mattina)
    db.refresh(pomeriggio)
    return mattina, pomeriggio


def test_generazione_da_pattern_rispetta_settimana_dispari_pari(client, crea_utente, db):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    sede = _crea_sede(db)
    mattina, pomeriggio = _crea_tipi_turno(db)
    dip = Dipendente(cognome="Test", nome="Pattern", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(PatternTurno(
        dipendente_id=dip.id,
        turno_settimana_dispari_id=mattina.id,
        turno_settimana_pari_id=pomeriggio.id,
    ))
    db.commit()

    anno, mese = 2026, 8
    r = client.post(
        "/calendario/genera",
        data={"sede_id": sede.id, "anno": anno, "mese": mese},
        follow_redirects=False,
    )
    assert r.status_code == 303

    numero_giorni = monthrange(anno, mese)[1]
    righe = db.query(AssegnazioneGiornaliera).filter_by(dipendente_id=dip.id).all()
    assert len(righe) == numero_giorni
    for riga in righe:
        assert riga.origine == "pattern"
        settimana_dispari = riga.data.isocalendar().week % 2 == 1
        atteso = mattina.id if settimana_dispari else pomeriggio.id
        assert riga.tipo_turno_id == atteso


def test_generazione_non_sovrascrive_modifica_manuale(client, crea_utente, db):
    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    sede = _crea_sede(db)
    mattina, pomeriggio = _crea_tipi_turno(db)
    dip = Dipendente(cognome="Test", nome="Manuale", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(PatternTurno(
        dipendente_id=dip.id,
        turno_settimana_dispari_id=mattina.id,
        turno_settimana_pari_id=pomeriggio.id,
    ))
    db.commit()

    anno, mese, giorno = 2026, 8, 5
    data_manuale = date(anno, mese, giorno).isoformat()
    client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": data_manuale, "tipo_turno_id": pomeriggio.id},
    )

    client.post("/calendario/genera", data={"sede_id": sede.id, "anno": anno, "mese": mese}, follow_redirects=False)

    riga = db.query(AssegnazioneGiornaliera).filter_by(dipendente_id=dip.id, data=date(anno, mese, giorno)).first()
    assert riga.origine == "manuale"
    assert riga.tipo_turno_id == pomeriggio.id


def test_modifica_cella_crea_e_poi_cancella(client, crea_utente, db):
    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    sede = _crea_sede(db)
    mattina, _ = _crea_tipi_turno(db)
    dip = Dipendente(cognome="Test", nome="Cella", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    data_cella = "2026-08-10"
    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": data_cella, "tipo_turno_id": mattina.id},
    )
    assert r.status_code == 200
    riga = db.query(AssegnazioneGiornaliera).filter_by(dipendente_id=dip.id, data=date(2026, 8, 10)).first()
    assert riga is not None
    assert riga.origine == "manuale"
    assert riga.tipo_turno_id == mattina.id

    r2 = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": data_cella, "tipo_turno_id": ""},
    )
    assert r2.status_code == 200
    riga_dopo = db.query(AssegnazioneGiornaliera).filter_by(dipendente_id=dip.id, data=date(2026, 8, 10)).first()
    assert riga_dopo is None


def test_consultazione_non_puo_generare_ne_modificare_cella(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")

    sede = _crea_sede(db)
    mattina, _ = _crea_tipi_turno(db)
    dip = Dipendente(cognome="Test", nome="Permessi", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r1 = client.post(
        "/calendario/genera",
        data={"sede_id": sede.id, "anno": 2026, "mese": 8},
        follow_redirects=False,
    )
    assert r1.status_code == 403

    r2 = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-10", "tipo_turno_id": mattina.id},
        follow_redirects=False,
    )
    assert r2.status_code == 403


def test_log_modifiche_per_pattern_e_cella(client, crea_utente, db):
    from app.models import LogModifica

    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    sede = _crea_sede(db)
    mattina, _ = _crea_tipi_turno(db)
    dip = Dipendente(cognome="Test", nome="Log", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        f"/dipendenti/{dip.id}/pattern",
        data={"turno_settimana_dispari_id": mattina.id, "turno_settimana_pari_id": ""},
    )
    log_pattern = db.query(LogModifica).filter_by(tabella="pattern_turno", record_id=dip.id).first()
    assert log_pattern is not None
    assert log_pattern.utente_id == admin.id

    client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-10", "tipo_turno_id": mattina.id},
    )
    log_cella = db.query(LogModifica).filter_by(tabella="assegnazioni_giornaliere", azione="creazione").first()
    assert log_cella is not None
    assert log_cella.utente_id == admin.id

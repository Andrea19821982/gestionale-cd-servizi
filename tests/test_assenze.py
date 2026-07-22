from datetime import date, time

from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, LogModifica, Sede, TipoTurno
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _crea_tipo_turno(db, etichetta="Mattina Test"):
    tipo = TipoTurno(etichetta=etichetta, ora_inizio=time(7, 0), ora_fine=time(13, 30))
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    return tipo


def _login_admin(client, crea_utente):
    return crea_utente("admin_test", "passwordsegreta", "amministratore"), login(client, "admin_test", "passwordsegreta")


def test_creazione_assenza_copre_celle_esistenti_e_nuove(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = _crea_tipo_turno(db)
    dip = Dipendente(cognome="Test", nome="Assenza", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    # Un giorno già pianificato da pattern dentro il periodo di assenza.
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 8, 12), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="pattern",
    ))
    db.commit()

    r = client.post(
        "/assenze/nuova",
        data={
            "dipendente_id": dip.id,
            "data_inizio": "2026-08-10",
            "data_fine": "2026-08-14",
            "tipo_assenza": "Ferie",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    righe = (
        db.query(AssegnazioneGiornaliera)
        .filter(
            AssegnazioneGiornaliera.dipendente_id == dip.id,
            AssegnazioneGiornaliera.data >= date(2026, 8, 10),
            AssegnazioneGiornaliera.data <= date(2026, 8, 14),
        )
        .all()
    )
    assert len(righe) == 5
    for riga in righe:
        assert riga.origine == "assenza"
        assert riga.tipo_turno_id is None


def test_assenza_sovrapposta_rifiutata(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Sovrapposta", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-14", "tipo_assenza": "Ferie"},
    )
    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-12", "data_fine": "2026-08-16", "tipo_assenza": "Malattia"},
    )
    assert r.status_code == 400


def test_assenza_data_fine_precede_inizio_rifiutata(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="DateInvertite", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-14", "data_fine": "2026-08-10", "tipo_assenza": "Ferie"},
    )
    assert r.status_code == 400


def test_cancellazione_assenza_libera_celle(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Cancellazione", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-12", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    assert assenza is not None

    r = client.post(f"/assenze/{assenza.id}/elimina", follow_redirects=False)
    assert r.status_code == 303

    assert db.query(Assenza).filter_by(id=assenza.id).first() is None
    righe_rimaste = (
        db.query(AssegnazioneGiornaliera)
        .filter(
            AssegnazioneGiornaliera.dipendente_id == dip.id,
            AssegnazioneGiornaliera.data >= date(2026, 8, 10),
            AssegnazioneGiornaliera.data <= date(2026, 8, 12),
        )
        .all()
    )
    assert righe_rimaste == []


def test_elenco_filtrato_per_dipendente_e_periodo(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip_a = Dipendente(cognome="A", nome="Uno", sede_riferimento_id=sede.id, attivo=True)
    dip_b = Dipendente(cognome="B", nome="Due", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([dip_a, dip_b])
    db.commit()
    db.refresh(dip_a)
    db.refresh(dip_b)

    # Valori liberi e non ambigui: "Ferie"/"Malattia" comparirebbero comunque
    # nel <datalist> di suggerimento del form, indipendentemente dal filtro.
    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip_a.id, "data_inizio": "2026-08-01", "data_fine": "2026-08-02", "tipo_assenza": "TipoUnicoA"},
    )
    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip_b.id, "data_inizio": "2026-09-01", "data_fine": "2026-09-02", "tipo_assenza": "TipoUnicoB"},
    )

    r = client.get(f"/assenze?dipendente_id={dip_a.id}")
    assert "TipoUnicoA" in r.text
    assert "TipoUnicoB" not in r.text

    r2 = client.get("/assenze?data_da=2026-09-01")
    assert "TipoUnicoB" in r2.text
    assert "TipoUnicoA" not in r2.text


def test_gestore_turni_puo_gestire_assenze(client, crea_utente, db):
    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Gestore", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Permesso"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_consultazione_non_puo_creare_ne_eliminare_assenza(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="SoloLettura", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
        follow_redirects=False,
    )
    assert r.status_code == 403

    assenza = Assenza(dipendente_id=dip.id, data_inizio=date(2026, 8, 10), data_fine=date(2026, 8, 11), tipo_assenza="Ferie")
    db.add(assenza)
    db.commit()
    r2 = client.post(f"/assenze/{assenza.id}/elimina", follow_redirects=False)
    assert r2.status_code == 403


def test_approvazione_mantiene_celle_coperte(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Approvazione", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    assert assenza.stato == "richiesta"

    r = client.post(f"/assenze/{assenza.id}/approva", follow_redirects=False)
    assert r.status_code == 303

    db.refresh(assenza)
    assert assenza.stato == "approvata"
    assert assenza.deciso_da is not None
    righe = (
        db.query(AssegnazioneGiornaliera)
        .filter(
            AssegnazioneGiornaliera.dipendente_id == dip.id,
            AssegnazioneGiornaliera.data >= date(2026, 8, 10),
            AssegnazioneGiornaliera.data <= date(2026, 8, 11),
        )
        .all()
    )
    assert len(righe) == 2
    assert all(r.origine == "assenza" for r in righe)


def test_rifiuto_libera_celle_ma_mantiene_storico(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Rifiuto", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    r = client.post(f"/assenze/{assenza.id}/rifiuta", follow_redirects=False)
    assert r.status_code == 303

    # Lo storico della richiesta e del rifiuto resta: la riga non viene eliminata.
    db.refresh(assenza)
    assert assenza.stato == "rifiutata"
    assert assenza.deciso_da is not None
    assert db.query(Assenza).filter_by(id=assenza.id).first() is not None

    # Ma le celle del calendario che copriva tornano libere.
    righe = (
        db.query(AssegnazioneGiornaliera)
        .filter(
            AssegnazioneGiornaliera.dipendente_id == dip.id,
            AssegnazioneGiornaliera.data >= date(2026, 8, 10),
            AssegnazioneGiornaliera.data <= date(2026, 8, 11),
        )
        .all()
    )
    assert righe == []


def test_dopo_rifiuto_lo_stesso_periodo_puo_essere_richiesto_di_nuovo(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Riprova", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    prima = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    client.post(f"/assenze/{prima.id}/rifiuta")

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_non_si_puo_approvare_o_rifiutare_due_volte(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Doppio", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    client.post(f"/assenze/{assenza.id}/approva")

    r = client.post(f"/assenze/{assenza.id}/approva", follow_redirects=False)
    assert r.status_code == 400
    r2 = client.post(f"/assenze/{assenza.id}/rifiuta", follow_redirects=False)
    assert r2.status_code == 400


def test_solo_amministratore_puo_approvare_o_rifiutare(client, crea_utente, db):
    crea_utente("gestore_appr", "passwordsegreta", "gestore_turni")
    login(client, "gestore_appr", "passwordsegreta")
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="RuoloApprova", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    r = client.post(f"/assenze/{assenza.id}/approva", follow_redirects=False)
    assert r.status_code == 403
    r2 = client.post(f"/assenze/{assenza.id}/rifiuta", follow_redirects=False)
    assert r2.status_code == 403


def test_log_modifiche_creazione_e_cancellazione_assenza(client, crea_utente, db):
    admin, _ = _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Log", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    assert assenza.creato_da == admin.id

    log_creazione = db.query(LogModifica).filter_by(tabella="assenze", azione="creazione").first()
    assert log_creazione is not None
    assert log_creazione.utente_id == admin.id

    client.post(f"/assenze/{assenza.id}/elimina")
    log_cancellazione = db.query(LogModifica).filter_by(tabella="assenze", azione="cancellazione").first()
    assert log_cancellazione is not None

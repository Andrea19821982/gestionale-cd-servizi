from datetime import date

from app.models import Dipendente, LogModifica, Sede, Sostituzione
from tests.conftest import login


def _crea_sede(db, nome="Sede Test", colore="#123456"):
    sede = Sede(nome=nome, colore_hex=colore, attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    return admin


def test_sostituzione_giorno_intero_mostra_sostituto_nel_calendario(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede_a = _crea_sede(db, "Sede Partenza", "#111111")
    sede_b = _crea_sede(db, "Sede Sostituto", "#e91e8c")
    partente = Dipendente(cognome="Partente", nome="Test", sede_riferimento_id=sede_a.id, attivo=True)
    sostituto = Dipendente(cognome="Sostituto", nome="Test", sede_riferimento_id=sede_b.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede_a.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede_a.id,
            "data": "2026-08-10",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r2 = client.get(f"/calendario?sede_id={sede_a.id}&anno=2026&mese=8")
    assert r2.status_code == 200
    assert "Sostituto" in r2.text
    assert "#e91e8c" in r2.text


def test_sostituzione_oraria_mostra_solo_badge(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede_a = _crea_sede(db, "Sede Partenza 2", "#111111")
    sede_b = _crea_sede(db, "Sede Sostituto 2", "#e91e8c")
    partente = Dipendente(cognome="PartenteOraria", nome="Test", sede_riferimento_id=sede_a.id, attivo=True)
    sostituto = Dipendente(cognome="SostitutoOrario", nome="Test", sede_riferimento_id=sede_b.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede_a.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede_a.id,
            "data": "2026-08-11",
            "ora_inizio": "09:00",
            "ora_fine": "11:00",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r2 = client.get(f"/calendario?sede_id={sede_a.id}&anno=2026&mese=8")
    assert "badge-sostituzione-oraria" in r2.text
    # Il nome del sostituto NON deve sovrascrivere la cella (niente overlay pieno)
    assert 'class="badge-sostituzione"' not in r2.text


def test_autosostituzione_rifiutata(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Solo", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": dip.id,
            "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": dip.id,
            "sede_arrivo_id": sede.id,
            "data": "2026-08-10",
        },
    )
    assert r.status_code == 400


def test_doppia_sostituzione_giorno_intero_rifiutata(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="Doppia", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_1 = Dipendente(cognome="Sost1", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_2 = Dipendente(cognome="Sost2", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto_1, sostituto_2])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto_1)
    db.refresh(sostituto_2)

    dati_base = {
        "dipendente_partente_id": partente.id,
        "sede_partenza_id": sede.id,
        "sede_arrivo_id": sede.id,
        "data": "2026-08-10",
    }
    r1 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_1.id},
        follow_redirects=False,
    )
    assert r1.status_code == 303
    r2 = client.post("/sostituzioni/nuova", data={**dati_base, "dipendente_sostituto_id": sostituto_2.id})
    assert r2.status_code == 400


def test_sostituzione_oraria_rifiutata_se_esiste_gia_giorno_intero(client, crea_utente, db):
    """Se il dipendente è già sostituito per l'intera giornata, non ha senso
    (ed è contraddittorio: chi lo sostituisce davvero in quelle ore?)
    aggiungere anche una sostituzione oraria per lo stesso giorno."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="GiaIntero", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_1 = Dipendente(cognome="Sost1", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_2 = Dipendente(cognome="Sost2", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto_1, sostituto_2])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto_1)
    db.refresh(sostituto_2)

    dati_base = {
        "dipendente_partente_id": partente.id,
        "sede_partenza_id": sede.id,
        "sede_arrivo_id": sede.id,
        "data": "2026-08-10",
    }
    r1 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_1.id},
        follow_redirects=False,
    )
    assert r1.status_code == 303

    r2 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_2.id, "ora_inizio": "09:00", "ora_fine": "11:00"},
    )
    assert r2.status_code == 400


def test_sostituzione_giorno_intero_rifiutata_se_esiste_gia_oraria(client, crea_utente, db):
    """Stesso controllo nel verso opposto: se esiste già una sostituzione
    oraria per quel giorno, non si può aggiungere una sostituzione per
    l'intera giornata con un altro sostituto."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="GiaOraria", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_1 = Dipendente(cognome="Sost1", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_2 = Dipendente(cognome="Sost2", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto_1, sostituto_2])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto_1)
    db.refresh(sostituto_2)

    dati_base = {
        "dipendente_partente_id": partente.id,
        "sede_partenza_id": sede.id,
        "sede_arrivo_id": sede.id,
        "data": "2026-08-10",
    }
    r1 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_1.id, "ora_inizio": "09:00", "ora_fine": "11:00"},
        follow_redirects=False,
    )
    assert r1.status_code == 303

    r2 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_2.id},
    )
    assert r2.status_code == 400


def test_sostituzioni_orarie_sovrapposte_rifiutate(client, crea_utente, db):
    """Due sostituzioni orarie per lo stesso dipendente nello stesso giorno,
    con fasce orarie che si sovrappongono (09-11 e 10-12), sono
    contraddittorie: due sostituti diversi non possono coprire la stessa ora."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="Sovrapposta", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_1 = Dipendente(cognome="Sost1", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_2 = Dipendente(cognome="Sost2", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto_1, sostituto_2])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto_1)
    db.refresh(sostituto_2)

    dati_base = {
        "dipendente_partente_id": partente.id,
        "sede_partenza_id": sede.id,
        "sede_arrivo_id": sede.id,
        "data": "2026-08-10",
    }
    r1 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_1.id, "ora_inizio": "09:00", "ora_fine": "11:00"},
        follow_redirects=False,
    )
    assert r1.status_code == 303

    r2 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_2.id, "ora_inizio": "10:00", "ora_fine": "12:00"},
    )
    assert r2.status_code == 400


def test_sostituzioni_orarie_non_sovrapposte_accettate(client, crea_utente, db):
    """Due sostituzioni orarie per lo stesso dipendente nello stesso giorno,
    ma su fasce orarie diverse e non sovrapposte (09-11 e 11-13), restano
    valide: sostituti diversi possono coprire ore diverse dello stesso giorno."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="NonSovrapposta", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_1 = Dipendente(cognome="Sost1", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto_2 = Dipendente(cognome="Sost2", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto_1, sostituto_2])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto_1)
    db.refresh(sostituto_2)

    dati_base = {
        "dipendente_partente_id": partente.id,
        "sede_partenza_id": sede.id,
        "sede_arrivo_id": sede.id,
        "data": "2026-08-10",
    }
    r1 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_1.id, "ora_inizio": "09:00", "ora_fine": "11:00"},
        follow_redirects=False,
    )
    assert r1.status_code == 303

    r2 = client.post(
        "/sostituzioni/nuova",
        data={**dati_base, "dipendente_sostituto_id": sostituto_2.id, "ora_inizio": "11:00", "ora_fine": "13:00"},
        follow_redirects=False,
    )
    assert r2.status_code == 303


def test_orario_incompleto_rifiutato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="Incompleto", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="Sost", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede.id,
            "data": "2026-08-10",
            "ora_inizio": "09:00",
        },
    )
    assert r.status_code == 400


def test_ora_fine_precede_inizio_rifiutata(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="OrarioInvertito", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="Sost", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede.id,
            "data": "2026-08-10",
            "ora_inizio": "11:00",
            "ora_fine": "09:00",
        },
    )
    assert r.status_code == 400


def test_consultazione_non_puo_creare_ne_eliminare_sostituzione(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    partente = Dipendente(cognome="SoloLettura1", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="SoloLettura2", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede.id,
            "data": "2026-08-10",
        },
        follow_redirects=False,
    )
    assert r.status_code == 403

    sostituzione = Sostituzione(
        data=date(2026, 8, 10), dipendente_partente_id=partente.id, sede_partenza_id=sede.id,
        dipendente_sostituto_id=sostituto.id, sede_arrivo_id=sede.id,
    )
    db.add(sostituzione)
    db.commit()
    r2 = client.post(f"/sostituzioni/{sostituzione.id}/elimina", follow_redirects=False)
    assert r2.status_code == 403


def test_log_modifiche_creazione_e_cancellazione_sostituzione(client, crea_utente, db):
    admin = _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    partente = Dipendente(cognome="Log1", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="Log2", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede.id,
            "data": "2026-08-10",
        },
    )
    sostituzione = db.query(Sostituzione).filter_by(dipendente_partente_id=partente.id).first()
    log_creazione = db.query(LogModifica).filter_by(tabella="sostituzioni", azione="creazione").first()
    assert log_creazione is not None
    assert log_creazione.utente_id == admin.id

    client.post(f"/sostituzioni/{sostituzione.id}/elimina")
    log_cancellazione = db.query(LogModifica).filter_by(tabella="sostituzioni", azione="cancellazione").first()
    assert log_cancellazione is not None


def test_elenco_filtrato_per_dipendente_e_periodo(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    a = Dipendente(cognome="ElencoA", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    b = Dipendente(cognome="ElencoB", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    c = Dipendente(cognome="ElencoC", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([a, b, c])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    db.refresh(c)

    client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": a.id, "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": b.id, "sede_arrivo_id": sede.id, "data": "2026-08-01",
        },
    )
    client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": c.id, "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": b.id, "sede_arrivo_id": sede.id, "data": "2026-09-01",
        },
    )

    r = client.get(f"/sostituzioni?dipendente_id={a.id}")
    assert "2026-08-01" in r.text
    assert "2026-09-01" not in r.text

    r2 = client.get("/sostituzioni?data_da=2026-09-01")
    assert "2026-09-01" in r2.text
    assert "2026-08-01" not in r2.text

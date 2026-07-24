from datetime import date, time

from app.auth import hash_password
from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Sede, Sostituzione, TipoTurno, Utente
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


def test_dipendente_puo_richiedere_assenza_per_se_stesso(client, db):
    sede = _crea_sede(db)
    dip, _ = _crea_dipendente_con_login(db, sede)
    login(client, "dip_test", "passwordsegreta")

    r = client.post(
        "/area-personale/richiedi-assenza",
        data={"tipo_assenza": "Ferie", "data_inizio": "2026-08-10", "data_fine": "2026-08-12", "note": "Test"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/area-personale"

    assenza = db.query(Assenza).filter(Assenza.dipendente_id == dip.id).one()
    assert assenza.stato == "richiesta"
    assert assenza.tipo_assenza == "Ferie"

    # La richiesta deve coprire subito il calendario, come quella
    # inserita dall'amministrativo con /assenze/nuova.
    celle = (
        db.query(AssegnazioneGiornaliera)
        .filter(AssegnazioneGiornaliera.dipendente_id == dip.id, AssegnazioneGiornaliera.data == date(2026, 8, 10))
        .one()
    )
    assert celle.origine == "assenza"


def test_dipendente_richiede_assenza_malattia_nasce_gia_approvata(client, db):
    """Anche nel self-service, "Malattia" salta l'approvazione: nasce già
    "approvata" (deciso_da nullo, deciso_il valorizzato) e copre subito
    il calendario esattamente come una richiesta normale."""
    sede = _crea_sede(db)
    dip, _ = _crea_dipendente_con_login(db, sede)
    login(client, "dip_test", "passwordsegreta")

    r = client.post(
        "/area-personale/richiedi-assenza",
        data={"tipo_assenza": "Malattia", "data_inizio": "2026-08-10", "data_fine": "2026-08-12", "note": "Test"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    assenza = db.query(Assenza).filter(Assenza.dipendente_id == dip.id).one()
    assert assenza.stato == "approvata"
    assert assenza.deciso_da is None
    assert assenza.deciso_il is not None

    celle = (
        db.query(AssegnazioneGiornaliera)
        .filter(AssegnazioneGiornaliera.dipendente_id == dip.id, AssegnazioneGiornaliera.data == date(2026, 8, 10))
        .one()
    )
    assert celle.origine == "assenza"


def test_dipendente_non_puo_richiedere_assenza_per_un_collega(client, db):
    """Anche forzando un dipendente_id diverso nel corpo della richiesta,
    la route non lo legge affatto: usa sempre e solo il dipendente
    collegato all'account autenticato (vedi _dipendente_del_richiedente)."""
    sede = _crea_sede(db)
    dip, _ = _crea_dipendente_con_login(db, sede)
    collega = Dipendente(cognome="Collega", nome="Bersaglio", sede_riferimento_id=sede.id, attivo=True)
    db.add(collega)
    db.commit()
    db.refresh(collega)

    login(client, "dip_test", "passwordsegreta")
    r = client.post(
        "/area-personale/richiedi-assenza",
        data={
            "dipendente_id": collega.id,  # ignorato: non è un parametro della route
            "tipo_assenza": "Ferie",
            "data_inizio": "2026-08-10",
            "data_fine": "2026-08-12",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    assert db.query(Assenza).filter(Assenza.dipendente_id == collega.id).count() == 0
    assenza = db.query(Assenza).filter(Assenza.dipendente_id == dip.id).one()
    assert assenza.tipo_assenza == "Ferie"


def test_area_personale_mostra_sostituzione_fatta_dal_dipendente(client, db):
    """Una sostituzione non tocca la riga di AssegnazioneGiornaliera di chi
    sostituisce (vedi crea_sostituzione in sostituzioni.py): senza questa
    vista il dipendente non saprebbe di dover andare in un'altra sede,
    dato che non ha accesso al calendario generale."""
    sede_partenza = _crea_sede(db, "Sede Partenza")
    sede_arrivo = _crea_sede(db, "Sede Arrivo")
    dip, _ = _crea_dipendente_con_login(db, sede_partenza)
    collega = Dipendente(cognome="Collega", nome="DaSostituire", sede_riferimento_id=sede_partenza.id, attivo=True)
    db.add(collega)
    db.commit()
    db.refresh(collega)

    db.add(Sostituzione(
        data=date(2026, 8, 15),
        dipendente_partente_id=collega.id,
        sede_partenza_id=sede_partenza.id,
        dipendente_sostituto_id=dip.id,
        sede_arrivo_id=sede_arrivo.id,
    ))
    db.commit()

    login(client, "dip_test", "passwordsegreta")
    r = client.get("/area-personale?anno=2026&mese=8")
    assert r.status_code == 200
    riga_15 = r.text.split(">15 (S)<")[1].split("</tr>")[0]
    assert "Sede Arrivo" in riga_15
    assert "Collega DaSostituire" in riga_15
    assert "Sostituisci" in riga_15


def test_area_personale_mostra_di_essere_sostituito(client, db):
    sede = _crea_sede(db)
    dip, _ = _crea_dipendente_con_login(db, sede)
    sostituto = Dipendente(cognome="Collega", nome="Sostituto", sede_riferimento_id=sede.id, attivo=True)
    db.add(sostituto)
    db.commit()
    db.refresh(sostituto)

    db.add(Sostituzione(
        data=date(2026, 8, 15),
        dipendente_partente_id=dip.id,
        sede_partenza_id=sede.id,
        dipendente_sostituto_id=sostituto.id,
        sede_arrivo_id=sede.id,
    ))
    db.commit()

    login(client, "dip_test", "passwordsegreta")
    r = client.get("/area-personale?anno=2026&mese=8")
    assert r.status_code == 200
    riga_15 = r.text.split(">15 (S)<")[1].split("</tr>")[0]
    assert "Sostituito da" in riga_15
    assert "Collega Sostituto" in riga_15


def test_area_personale_non_mostra_sostituzioni_di_altri_giorni(client, db):
    """La sostituzione di un collega, in un'altra data, non deve comparire
    da nessuna parte nella pagina di chi non c'entra nulla."""
    sede = _crea_sede(db)
    dip, _ = _crea_dipendente_con_login(db, sede)
    altro1 = Dipendente(cognome="Altro", nome="Uno", sede_riferimento_id=sede.id, attivo=True)
    altro2 = Dipendente(cognome="Altro", nome="Due", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([altro1, altro2])
    db.commit()
    db.refresh(altro1)
    db.refresh(altro2)

    db.add(Sostituzione(
        data=date(2026, 8, 15),
        dipendente_partente_id=altro1.id,
        sede_partenza_id=sede.id,
        dipendente_sostituto_id=altro2.id,
        sede_arrivo_id=sede.id,
    ))
    db.commit()

    login(client, "dip_test", "passwordsegreta")
    r = client.get("/area-personale?anno=2026&mese=8")
    assert r.status_code == 200
    assert "Sostituisci" not in r.text
    assert "Sostituito da" not in r.text


def test_richiedi_assenza_richiede_ruolo_dipendente(client, crea_utente):
    crea_utente("gestore_areapersonale_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_areapersonale_test", "passwordsegreta")

    r = client.post(
        "/area-personale/richiedi-assenza",
        data={"tipo_assenza": "Ferie", "data_inizio": "2026-08-10", "data_fine": "2026-08-12"},
        follow_redirects=False,
    )
    assert r.status_code == 403

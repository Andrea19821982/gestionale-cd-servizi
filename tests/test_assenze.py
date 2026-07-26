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


def test_assenza_malattia_nasce_gia_approvata(client, crea_utente, db):
    """La malattia non richiede approvazione: nasce già "approvata", con
    deciso_il valorizzato ma deciso_da nullo (nessuna persona ha deciso,
    è stata approvata automaticamente) e copre subito il calendario."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Malattia", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    assert assenza.stato == "approvata"
    assert assenza.deciso_da is None
    assert assenza.deciso_il is not None

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
    assert all(riga.origine == "assenza" for riga in righe)


def test_assenza_ferie_resta_richiesta(client, crea_utente, db):
    """Nessuna regressione: un tipo diverso da "Malattia" continua a
    restare "richiesta" in attesa di approvazione."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Ferie", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    assert assenza.stato == "richiesta"
    assert assenza.deciso_da is None
    assert assenza.deciso_il is None


def test_assenza_malattia_case_insensitive_e_non_sottostringa(client, crea_utente, db):
    """Il confronto è tollerante a maiuscole/spazi ma esatto sull'intera
    stringa: "MALATTIA " approva automaticamente, mentre un tipo che
    contiene "malattia" come sottostringa (es. "Malattia lunga") o un
    tipo diverso (es. "Permesso") resta "richiesta"."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)

    dip1 = Dipendente(cognome="Test", nome="MalattiaMaiuscola", sede_riferimento_id=sede.id, attivo=True)
    dip2 = Dipendente(cognome="Test", nome="MalattiaLunga", sede_riferimento_id=sede.id, attivo=True)
    dip3 = Dipendente(cognome="Test", nome="Permesso", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([dip1, dip2, dip3])
    db.commit()
    for d in (dip1, dip2, dip3):
        db.refresh(d)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip1.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "MALATTIA "},
    )
    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip2.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia lunga"},
    )
    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip3.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Permesso"},
    )

    assert db.query(Assenza).filter_by(dipendente_id=dip1.id).first().stato == "approvata"
    assert db.query(Assenza).filter_by(dipendente_id=dip2.id).first().stato == "richiesta"
    assert db.query(Assenza).filter_by(dipendente_id=dip3.id).first().stato == "richiesta"


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


def _dipendente_con_turno_pianificato(client, crea_utente, db, giorno=date(2026, 8, 12)):
    """Scenario di partenza dei test qui sotto: un dipendente con un turno
    già assegnato a mano nel giorno che l'assenza andrà a coprire."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Ripristino")
    tipo = _crea_tipo_turno(db, "Mattina Ripristino")
    dip = Dipendente(cognome="Ripristino", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=giorno, sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()
    return dip, tipo, giorno


def _crea_assenza(client, dip, giorno):
    client.post(
        "/assenze/nuova",
        data={
            "dipendente_id": dip.id,
            "data_inizio": giorno.isoformat(),
            "data_fine": giorno.isoformat(),
            "tipo_assenza": "Ferie",
        },
        follow_redirects=False,
    )


def _assegnazione(db, dip, giorno):
    return (
        db.query(AssegnazioneGiornaliera)
        .filter_by(dipendente_id=dip.id, data=giorno)
        .first()
    )


def test_rifiutare_un_assenza_restituisce_il_turno_che_era_pianificato(client, crea_utente, db):
    """Il caso che prima distruggeva dati: si registrano le ferie di chi
    aveva già turni assegnati a mano, il responsabile le rifiuta, e i turni
    erano persi per sempre — nemmeno il registro delle modifiche li
    conservava, quindi nessuno poteva ricostruirli."""
    dip, tipo, giorno = _dipendente_con_turno_pianificato(client, crea_utente, db)
    _crea_assenza(client, dip, giorno)

    db.expire_all()
    coperta = _assegnazione(db, dip, giorno)
    assert coperta.origine == "assenza"
    assert coperta.tipo_turno_id is None  # l'assenza prevale, come previsto

    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    client.post(f"/assenze/{assenza.id}/rifiuta", follow_redirects=False)

    db.expire_all()
    ripristinata = _assegnazione(db, dip, giorno)
    assert ripristinata is not None, "la cella non deve sparire: c'era un turno"
    assert ripristinata.tipo_turno_id == tipo.id
    assert ripristinata.origine == "manuale"
    assert ripristinata.origine_precedente is None  # memoria consumata


def test_cancellare_un_assenza_restituisce_il_turno_che_era_pianificato(client, crea_utente, db):
    dip, tipo, giorno = _dipendente_con_turno_pianificato(client, crea_utente, db)
    _crea_assenza(client, dip, giorno)
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    client.post(f"/assenze/{assenza.id}/elimina", follow_redirects=False)

    db.expire_all()
    ripristinata = _assegnazione(db, dip, giorno)
    assert ripristinata is not None
    assert ripristinata.tipo_turno_id == tipo.id
    assert ripristinata.origine == "manuale"


def test_cella_creata_dall_assenza_viene_rimossa_e_non_lascia_un_turno_vuoto(client, crea_utente, db):
    """Il contraltare: dove non c'era nessun turno, l'assenza ha creato lei
    la cella e al rifiuto va tolta, non lasciata come giornata vuota."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Senza Turno")
    dip = Dipendente(cognome="SenzaTurno", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    giorno = date(2026, 8, 20)

    _crea_assenza(client, dip, giorno)
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    client.post(f"/assenze/{assenza.id}/rifiuta", follow_redirects=False)

    db.expire_all()
    assert _assegnazione(db, dip, giorno) is None


def test_due_assenze_sovrapposte_non_perdono_la_memoria_del_turno_vero(client, crea_utente, db):
    """Se una seconda assenza copre un giorno già coperto dalla prima, non
    deve registrare come "precedente" il vuoto lasciato dalla prima: quello
    cancellerebbe la memoria del turno vero, che è ciò che va restituito."""
    dip, tipo, giorno = _dipendente_con_turno_pianificato(client, crea_utente, db)
    _crea_assenza(client, dip, giorno)

    # Seconda copertura dello stesso giorno, simulata chiamando
    # direttamente la funzione: via HTTP il controllo di sovrapposizione la
    # rifiuterebbe, ma la protezione deve reggere comunque.
    from app.routers.assenze import _copri_giorni_con_assenza

    db.expire_all()
    _copri_giorni_con_assenza(db, db.get(Dipendente, dip.id), giorno, giorno)
    db.commit()

    riga = _assegnazione(db, dip, giorno)
    assert riga.tipo_turno_precedente_id == tipo.id
    assert riga.origine_precedente == "manuale"

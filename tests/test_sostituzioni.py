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


def _scenario_sostituto(client, crea_utente, db):
    """Due dipendenti da sostituire e un unico sostituto conteso, ciascuno
    con la propria sede: lo scenario dei test qui sotto."""
    _login_admin(client, crea_utente)
    sede_a = _crea_sede(db, "Palazzo A", "#111111")
    sede_b = _crea_sede(db, "Palazzo B", "#222222")
    primo = Dipendente(cognome="PrimoAssente", nome="Test", sede_riferimento_id=sede_a.id, attivo=True)
    secondo = Dipendente(cognome="SecondoAssente", nome="Test", sede_riferimento_id=sede_b.id, attivo=True)
    sostituto = Dipendente(cognome="Conteso", nome="Test", sede_riferimento_id=sede_a.id, attivo=True)
    db.add_all([primo, secondo, sostituto])
    db.commit()
    for d in (primo, secondo, sostituto):
        db.refresh(d)
    return sede_a, sede_b, primo, secondo, sostituto


def _posta_sostituzione(client, partente, sede_partenza, sostituto, sede_arrivo, giorno, ora_inizio="", ora_fine=""):
    return client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede_partenza.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede_arrivo.id,
            "data": giorno,
            "ora_inizio": ora_inizio,
            "ora_fine": ora_fine,
        },
        follow_redirects=False,
    )


def test_stesso_sostituto_non_puo_coprire_due_sedi_nello_stesso_giorno(client, crea_utente, db):
    """Il controllo di conflitto guardava solo chi VIENE sostituito: la
    stessa persona poteva risultare contemporaneamente in due palazzi, e il
    buco si scopriva quando al presidio non si presentava nessuno."""
    sede_a, sede_b, primo, secondo, sostituto = _scenario_sostituto(client, crea_utente, db)

    prima = _posta_sostituzione(client, primo, sede_a, sostituto, sede_a, "2026-09-10")
    assert prima.status_code == 303

    seconda = _posta_sostituzione(client, secondo, sede_b, sostituto, sede_b, "2026-09-10")

    assert seconda.status_code == 400
    assert db.query(Sostituzione).count() == 1


def test_stesso_sostituto_su_fasce_orarie_sovrapposte_rifiutato(client, crea_utente, db):
    sede_a, sede_b, primo, secondo, sostituto = _scenario_sostituto(client, crea_utente, db)

    prima = _posta_sostituzione(client, primo, sede_a, sostituto, sede_a, "2026-09-11", "09:00", "13:00")
    assert prima.status_code == 303

    seconda = _posta_sostituzione(client, secondo, sede_b, sostituto, sede_b, "2026-09-11", "11:00", "15:00")

    assert seconda.status_code == 400
    assert db.query(Sostituzione).count() == 1


def test_stesso_sostituto_su_fasce_che_non_si_toccano_e_permesso(client, crea_utente, db):
    """Il contraltare: chi copre 9-11 in un palazzo può coprire 11-13 in un
    altro. Bloccarlo sarebbe stato più comodo da programmare e sbagliato."""
    sede_a, sede_b, primo, secondo, sostituto = _scenario_sostituto(client, crea_utente, db)

    prima = _posta_sostituzione(client, primo, sede_a, sostituto, sede_a, "2026-09-12", "09:00", "11:00")
    seconda = _posta_sostituzione(client, secondo, sede_b, sostituto, sede_b, "2026-09-12", "11:00", "13:00")

    assert prima.status_code == 303
    assert seconda.status_code == 303
    assert db.query(Sostituzione).count() == 2


def test_non_si_puo_mandare_a_sostituire_chi_e_in_ferie(client, crea_utente, db):
    """Mandare a coprire un presidio una persona che quel giorno è in ferie
    è un buco garantito: il programma lo accettava senza dire niente."""
    sede_a, sede_b, primo, secondo, sostituto = _scenario_sostituto(client, crea_utente, db)

    client.post(
        "/assenze/nuova",
        data={
            "dipendente_id": sostituto.id,
            "data_inizio": "2026-09-15",
            "data_fine": "2026-09-15",
            "tipo_assenza": "Ferie",
        },
        follow_redirects=False,
    )

    r = _posta_sostituzione(client, primo, sede_a, sostituto, sede_a, "2026-09-15")

    assert r.status_code == 400
    assert "assente" in r.text.lower()
    assert db.query(Sostituzione).count() == 0


def test_sostituto_libero_in_un_altro_giorno_resta_assegnabile(client, crea_utente, db):
    """Le restrizioni valgono per lo stesso giorno, non in generale."""
    sede_a, sede_b, primo, secondo, sostituto = _scenario_sostituto(client, crea_utente, db)

    prima = _posta_sostituzione(client, primo, sede_a, sostituto, sede_a, "2026-09-20")
    seconda = _posta_sostituzione(client, secondo, sede_b, sostituto, sede_b, "2026-09-21")

    assert prima.status_code == 303
    assert seconda.status_code == 303
    assert db.query(Sostituzione).count() == 2


def test_i_parametri_precompila_riempiono_il_form(client, crea_utente, db):
    """I parametri arrivano dal pulsante "Organizza sostituzione" della
    pagina Copertura: chi manca, il palazzo e il giorno sono già noti da
    lì, e vanno preselezionati nel form invece di essere reinseriti a
    memoria da una tendina di decine di nomi."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Precompila")
    dip = Dipendente(cognome="Precompilato", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get(
        f"/sostituzioni?precompila_partente_id={dip.id}"
        f"&precompila_sede_id={sede.id}&precompila_data=2026-08-15"
    )

    assert r.status_code == 200
    testo = r.text
    assert f'<option value="{dip.id}" data-sede="{sede.id}" selected>' in testo
    # Sede partenza E sede arrivo devono precompilarsi entrambe con la sede
    # dell'assente: il sostituto va mandato proprio dove manca la persona.
    assert testo.count(f'<option value="{sede.id}" selected>') == 2
    assert 'value="2026-08-15"' in testo
    assert "Compilato dalla pagina Copertura" in testo


def test_senza_parametri_precompila_il_form_resta_vuoto_come_prima(client, crea_utente, db):
    """Un utente che apre /sostituzioni normalmente non deve trovare nulla
    di preselezionato né l'avviso di precompilazione."""
    _login_admin(client, crea_utente)

    r = client.get("/sostituzioni")

    assert "Compilato dalla pagina Copertura" not in r.text
    assert '<option value="" disabled selected>— scegli —</option>' in r.text


def test_precompila_data_non_valida_da_errore_leggibile_non_pagina_bianca(client, crea_utente, db):
    """Se l'indirizzo arrivasse con una data malformata, deve fallire con
    l'errore leggibile del gestore centrale, non con un campo silenziosamente
    vuoto che lascerebbe l'utente a chiedersi perché la data non c'è."""
    _login_admin(client, crea_utente)

    r = client.get("/sostituzioni?precompila_data=non-una-data", headers={"accept": "text/html"})

    assert r.status_code == 400
    assert "Non è stato possibile salvare" in r.text or "non valida" in r.text.lower()


def test_creare_la_sostituzione_precompilata_funziona_dal_form_al_salvataggio(client, crea_utente, db):
    """Il test end-to-end del pulsante: apre il form con i parametri della
    Copertura, sceglie solo il sostituto (l'unico campo lasciato vuoto) e
    verifica che la sostituzione nasca con i dati giusti."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Flusso Completo")
    partente = Dipendente(cognome="PartenteFlusso", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="SostitutoFlusso", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([partente, sostituto])
    db.commit()
    db.refresh(partente)
    db.refresh(sostituto)

    pagina = client.get(
        f"/sostituzioni?precompila_partente_id={partente.id}"
        f"&precompila_sede_id={sede.id}&precompila_data=2026-08-20"
    )
    assert pagina.status_code == 200

    r = client.post(
        "/sostituzioni/nuova",
        data={
            "dipendente_partente_id": partente.id,
            "sede_partenza_id": sede.id,
            "dipendente_sostituto_id": sostituto.id,
            "sede_arrivo_id": sede.id,
            "data": "2026-08-20",
        },
        follow_redirects=False,
    )

    assert r.status_code == 303
    creata = db.query(Sostituzione).filter_by(dipendente_partente_id=partente.id).first()
    assert creata is not None
    assert creata.dipendente_sostituto_id == sostituto.id
    assert creata.data == date(2026, 8, 20)


def test_sostituzione_giorno_intero_colora_il_bordo_di_blu(client, crea_utente, db):
    """assegnazione.origine non diventa mai "sostituzione" (nessuna rotta
    scrive quel valore lì: crea_sostituzione non tocca la riga del
    partente), quindi il bordo blu della legenda non poteva mai comparire
    finché il colore veniva dedotto solo da quel campo. Il colore va
    dedotto da sostituzioni_giorno, la stessa fonte che già pesca il nome
    del sostituto per il badge sotto la cella."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Bordo Blu")
    partente = Dipendente(cognome="PartenteBordo", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="SostitutoBordo", nome="Test", sede_riferimento_id=sede.id, attivo=True)
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
            "data": "2026-08-14",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r2 = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=8")
    cella = r2.text.split(f'cella-{partente.id}-2026-08-14')[1].split("</td>")[0]
    assert "origine-sostituzione" in cella


def test_sostituzione_oraria_non_colora_il_bordo_di_blu(client, crea_utente, db):
    """Il contraltare: una sostituzione di poche ore non deve nascondere il
    turno di base della persona, che lavora comunque il resto della
    giornata. Solo il tag "S 9:00-11:00" deve comparire."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Bordo Orario")
    partente = Dipendente(cognome="PartenteBordoOrario", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    sostituto = Dipendente(cognome="SostitutoBordoOrario", nome="Test", sede_riferimento_id=sede.id, attivo=True)
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
            "data": "2026-08-16",
            "ora_inizio": "09:00",
            "ora_fine": "11:00",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r2 = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=8")
    cella = r2.text.split(f'cella-{partente.id}-2026-08-16')[1].split("</td>")[0]
    assert "origine-sostituzione" not in cella
    assert "badge-sostituzione-oraria" in cella

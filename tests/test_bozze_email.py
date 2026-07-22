from datetime import date

from app import email_config
from app.models import AssegnazioneGiornaliera, Assenza, BozzaEmail, Dipendente, Sede, Sostituzione
from app.routers.bozze_email import genera_testo_email_dipendenti
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _crea_dipendente(db, cognome, nome, sede):
    dip = Dipendente(cognome=cognome, nome=nome, sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def _crea_bozza_assenza(db, dipendente, con_errore=False):
    bozza = BozzaEmail(
        tipo="assenza",
        stato="da_confermare",
        mittente="dipendente@esempio.it",
        oggetto="ASSENZA",
        corpo="Nome: Test\nTipo: Ferie\nDal: 10/08/2026\nAl: 11/08/2026\n",
        dipendente_id=dipendente.id if not con_errore else None,
        tipo_assenza="Ferie",
        data_inizio=date(2026, 8, 10),
        data_fine=date(2026, 8, 11),
        errore_parsing="dipendente non trovato: 'X'" if con_errore else None,
    )
    db.add(bozza)
    db.commit()
    db.refresh(bozza)
    return bozza


def _crea_bozza_sostituzione(db, assente, sostituto):
    bozza = BozzaEmail(
        tipo="sostituzione",
        stato="da_confermare",
        mittente="dipendente@esempio.it",
        oggetto="SOSTITUZIONE",
        corpo="Data: 10/08/2026\nAssente: Test\nSostituto: Test2\nOrario: intera giornata\n",
        dipendente_id=assente.id,
        dipendente_sostituto_id=sostituto.id,
        data_inizio=date(2026, 8, 10),
        data_fine=date(2026, 8, 10),
    )
    db.add(bozza)
    db.commit()
    db.refresh(bozza)
    return bozza


def test_elenco_bozze_email_mostra_avviso_di_errore(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = _crea_dipendente(db, "Rossi", "Mario", sede)
    _crea_bozza_assenza(db, dip, con_errore=True)

    r = client.get("/bozze-email")
    assert r.status_code == 200
    assert "Da controllare" in r.text


def test_conferma_bozza_assenza_crea_assenza_e_copre_calendario(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = _crea_dipendente(db, "Rossi", "Mario", sede)
    bozza = _crea_bozza_assenza(db, dip)

    r = client.post(
        f"/bozze-email/{bozza.id}/conferma",
        data={
            "dipendente_id": dip.id,
            "tipo_assenza": "Ferie",
            "data_inizio": "2026-08-10",
            "data_fine": "2026-08-11",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.refresh(bozza)
    assert bozza.stato == "confermata"
    assert bozza.record_creato_tabella == "assenze"
    assenza = db.query(Assenza).filter_by(id=bozza.record_creato_id).first()
    assert assenza is not None
    assert assenza.dipendente_id == dip.id
    assert assenza.stato == "richiesta"

    righe = db.query(AssegnazioneGiornaliera).filter(
        AssegnazioneGiornaliera.dipendente_id == dip.id,
        AssegnazioneGiornaliera.data >= date(2026, 8, 10),
        AssegnazioneGiornaliera.data <= date(2026, 8, 11),
    ).all()
    assert len(righe) == 2
    assert all(r.origine == "assenza" for r in righe)


def test_conferma_bozza_sostituzione_crea_sostituzione(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    assente = _crea_dipendente(db, "Rossi", "Mario", sede)
    sostituto = _crea_dipendente(db, "Verdi", "Luca", sede)
    bozza = _crea_bozza_sostituzione(db, assente, sostituto)

    r = client.post(
        f"/bozze-email/{bozza.id}/conferma",
        data={
            "dipendente_id": assente.id,
            "dipendente_sostituto_id": sostituto.id,
            "data_inizio": "2026-08-10",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.refresh(bozza)
    assert bozza.stato == "confermata"
    assert bozza.record_creato_tabella == "sostituzioni"
    sostituzione = db.query(Sostituzione).filter_by(id=bozza.record_creato_id).first()
    assert sostituzione is not None
    assert sostituzione.dipendente_partente_id == assente.id
    assert sostituzione.dipendente_sostituto_id == sostituto.id
    assert sostituzione.sede_partenza_id == sede.id
    assert sostituzione.sede_arrivo_id == sede.id


def test_scarta_bozza_non_crea_nulla(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = _crea_dipendente(db, "Rossi", "Mario", sede)
    bozza = _crea_bozza_assenza(db, dip)

    r = client.post(f"/bozze-email/{bozza.id}/scarta", follow_redirects=False)
    assert r.status_code == 303

    db.refresh(bozza)
    assert bozza.stato == "scartata"
    assert db.query(Assenza).count() == 0


def test_non_si_puo_confermare_o_scartare_due_volte(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = _crea_dipendente(db, "Rossi", "Mario", sede)
    bozza = _crea_bozza_assenza(db, dip)

    client.post(f"/bozze-email/{bozza.id}/scarta")

    r = client.post(f"/bozze-email/{bozza.id}/scarta", follow_redirects=False)
    assert r.status_code == 400
    r2 = client.post(
        f"/bozze-email/{bozza.id}/conferma",
        data={"dipendente_id": dip.id, "tipo_assenza": "Ferie", "data_inizio": "2026-08-10", "data_fine": "2026-08-11"},
        follow_redirects=False,
    )
    assert r2.status_code == 400


def test_consultazione_non_accede_alle_bozze_email(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/bozze-email", follow_redirects=False)
    assert r.status_code == 403


def test_genera_testo_email_dipendenti_contiene_indirizzo_e_formati():
    testo = genera_testo_email_dipendenti("turni@cdservizi.it")
    assert "turni@cdservizi.it" in testo
    assert "ASSENZA" in testo
    assert "SOSTITUZIONE" in testo
    assert "Nome: Cognome Nome" in testo
    assert "Data: gg/mm/aaaa" in testo


def test_genera_testo_email_dipendenti_senza_indirizzo_mostra_segnaposto():
    testo = genera_testo_email_dipendenti("")
    assert "[inserisci qui l'indirizzo email dedicato]" in testo


def test_pagina_bozze_email_mostra_sezione_testo_da_inoltrare(client, crea_utente, monkeypatch):
    monkeypatch.setattr(email_config, "IMAP_UTENTE", "turni@cdservizi.it")
    _login_admin(client, crea_utente)

    r = client.get("/bozze-email")

    assert r.status_code == 200
    assert "Testo da inoltrare ai dipendenti" in r.text
    assert "turni@cdservizi.it" in r.text
    assert "badge-warn-testo" not in r.text.split("Testo da inoltrare")[1].split("</details>")[0]


def test_pagina_bozze_email_avvisa_se_indirizzo_non_configurato(client, crea_utente, monkeypatch):
    monkeypatch.setattr(email_config, "IMAP_UTENTE", "")
    _login_admin(client, crea_utente)

    r = client.get("/bozze-email")

    assert r.status_code == 200
    assert "non è ancora configurato" in r.text

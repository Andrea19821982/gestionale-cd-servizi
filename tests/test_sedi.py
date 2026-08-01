from app.models import Dipendente, Sede, SottosezioneCopertura
from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_sedi_test", "passwordsegreta", "amministratore")
    login(client, "admin_sedi_test", "passwordsegreta")


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def test_crea_sede_con_minimi_mattina_pomeriggio(client, crea_utente, db):
    _login_admin(client, crea_utente)
    r = client.post(
        "/sedi/nuova",
        data={
            "nome": "Sede Fasce Test", "colore_hex": "#2563eb",
            "copertura_minima_mattina": "3", "copertura_minima_pomeriggio": "2",
            "ordine_visualizzazione": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    sede = db.query(Sede).filter_by(nome="Sede Fasce Test").first()
    assert sede.copertura_minima_mattina == 3
    assert sede.copertura_minima_pomeriggio == 2


def test_modifica_sede_aggiorna_minimi_mattina_pomeriggio(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)

    r = client.post(
        f"/sedi/{sede.id}/modifica",
        data={
            "nome": sede.nome, "colore_hex": sede.colore_hex,
            "copertura_minima_mattina": "5", "copertura_minima_pomeriggio": "1",
            "ordine_visualizzazione": "0", "attivo": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.refresh(sede)
    assert sede.copertura_minima_mattina == 5
    assert sede.copertura_minima_pomeriggio == 1


def test_crea_sede_con_minimo_negativo_da_400(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/sedi/nuova",
        data={
            "nome": "Sede Negativa", "colore_hex": "#2563eb",
            "copertura_minima_mattina": "-1", "copertura_minima_pomeriggio": "0",
            "ordine_visualizzazione": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_crea_comparto_copertura(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Con Comparto")

    r = client.post(
        "/sedi/comparti/nuovo",
        data={
            "sede_id": sede.id, "nome": "Parcheggio",
            "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    comparto = db.query(SottosezioneCopertura).filter_by(sede_id=sede.id, nome="Parcheggio").first()
    assert comparto is not None
    assert comparto.copertura_minima_mattina == 1
    assert comparto.copertura_minima_pomeriggio == 1


def test_modifica_comparto_copertura(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Con Comparto Da Modificare")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Archivio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    db.commit()
    db.refresh(comparto)

    r = client.post(
        f"/sedi/comparti/{comparto.id}/modifica",
        data={
            "sede_id": sede.id, "nome": "Archivio legislativo",
            "copertura_minima_mattina": "2", "copertura_minima_pomeriggio": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.refresh(comparto)
    assert comparto.nome == "Archivio legislativo"
    assert comparto.copertura_minima_mattina == 2


def _crea_dipendente(db, cognome, sede, sottosezione=None):
    dip = Dipendente(cognome=cognome, nome="Test", sede_riferimento_id=sede.id, attivo=True, sottosezione=sottosezione)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def test_crea_comparto_assegnando_subito_i_dipendenti(client, crea_utente, db):
    """Creando il comparto si può già spuntare chi ne fa parte, senza
    doverli poi aprire uno a uno da Dipendenti."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Con Membri")
    dip_dentro = _crea_dipendente(db, "Dentro", sede)
    dip_fuori = _crea_dipendente(db, "Fuori", sede)

    r = client.post(
        "/sedi/comparti/nuovo",
        data={
            "sede_id": sede.id, "nome": "Parcheggio",
            "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1",
            "dipendente_ids": [str(dip_dentro.id)],
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.expire_all()
    assert db.get(Dipendente, dip_dentro.id).sottosezione == "Parcheggio"
    assert db.get(Dipendente, dip_fuori.id).sottosezione is None


def test_modifica_comparto_aggiunge_e_toglie_membri(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Membri Modifica")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    db.commit()
    db.refresh(comparto)
    gia_dentro = _crea_dipendente(db, "GiaDentro", sede, sottosezione="Parcheggio")
    da_aggiungere = _crea_dipendente(db, "DaAggiungere", sede)

    r = client.post(
        f"/sedi/comparti/{comparto.id}/modifica",
        data={
            "sede_id": sede.id, "nome": "Parcheggio",
            "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1",
            "dipendente_ids": [str(da_aggiungere.id)],  # gia_dentro non è più spuntato
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.expire_all()
    assert db.get(Dipendente, da_aggiungere.id).sottosezione == "Parcheggio"
    assert db.get(Dipendente, gia_dentro.id).sottosezione is None


def test_modifica_comparto_non_ruba_i_membri_di_un_altro_comparto(client, crea_utente, db):
    """Chi è già in un altro comparto della stessa sede non deve essere
    svuotato solo perché non è spuntato in questo form (nel template è
    disabilitato, ma il controllo deve reggere anche a una POST diretta)."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Due Comparti")
    parcheggio = SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(parcheggio)
    db.add(SottosezioneCopertura(sede_id=sede.id, nome="Archivio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1))
    db.commit()
    db.refresh(parcheggio)
    archivista = _crea_dipendente(db, "Archivista", sede, sottosezione="Archivio")

    r = client.post(
        f"/sedi/comparti/{parcheggio.id}/modifica",
        data={
            "sede_id": sede.id, "nome": "Parcheggio",
            "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.expire_all()
    assert db.get(Dipendente, archivista.id).sottosezione == "Archivio"


def test_rinominare_un_comparto_porta_con_se_i_suoi_dipendenti(client, crea_utente, db):
    """Rinominando il comparto, i dipendenti restavano col vecchio nome
    scritto in Sottosezione: scollegati dal minimo di copertura senza
    nessun avviso (stesso effetto del bug già corretto sulle maiuscole)."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Rinominato")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    db.commit()
    db.refresh(comparto)
    membro = _crea_dipendente(db, "Membro", sede, sottosezione="Parcheggio")

    r = client.post(
        f"/sedi/comparti/{comparto.id}/modifica",
        data={
            "sede_id": sede.id, "nome": "Parcheggio interrato",
            "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1",
            "dipendente_ids": [str(membro.id)],
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.expire_all()
    assert db.get(Dipendente, membro.id).sottosezione == "Parcheggio interrato"


def test_crea_comparto_duplicato_per_maiuscole_da_400(client, crea_utente, db):
    """Due comparti nella stessa sede che differiscono solo per maiuscole o
    spazi collasserebbero sulla stessa chiave in calcola_copertura, facendo
    sparire silenziosamente il minimo di uno dei due: va rifiutato subito."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Duplicato")
    db.add(SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1))
    db.commit()

    r = client.post(
        "/sedi/comparti/nuovo",
        data={"sede_id": sede.id, "nome": "  parcheggio  ", "copertura_minima_mattina": "2", "copertura_minima_pomeriggio": "2"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert db.query(SottosezioneCopertura).filter_by(sede_id=sede.id).count() == 1


def test_stesso_nome_comparto_in_sedi_diverse_e_ammesso(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede_a = _crea_sede(db, "Sede Comparto A")
    sede_b = _crea_sede(db, "Sede Comparto B")
    db.add(SottosezioneCopertura(sede_id=sede_a.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1))
    db.commit()

    r = client.post(
        "/sedi/comparti/nuovo",
        data={"sede_id": sede_b.id, "nome": "Parcheggio", "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db.query(SottosezioneCopertura).filter_by(sede_id=sede_b.id, nome="Parcheggio").first() is not None


def test_modifica_comparto_in_duplicato_da_400(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Modifica Duplicato")
    db.add(SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1))
    comparto_b = SottosezioneCopertura(sede_id=sede.id, nome="Archivio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto_b)
    db.commit()
    db.refresh(comparto_b)

    r = client.post(
        f"/sedi/comparti/{comparto_b.id}/modifica",
        data={"sede_id": sede.id, "nome": "PARCHEGGIO", "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    db.refresh(comparto_b)
    assert comparto_b.nome == "Archivio"  # non modificato


def test_pagina_sedi_mostra_comparti_esistenti(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Con Comparto Visibile")
    db.add(SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1))
    db.commit()

    r = client.get("/sedi")
    assert r.status_code == 200
    assert "Parcheggio" in r.text


def test_comparti_richiede_amministratore_per_creare(client, crea_utente, db):
    crea_utente("gestore_sedi_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_sedi_test", "passwordsegreta")
    sede = _crea_sede(db, "Sede Gestore Test")

    r = client.post(
        "/sedi/comparti/nuovo",
        data={"sede_id": sede.id, "nome": "Parcheggio", "copertura_minima_mattina": "1", "copertura_minima_pomeriggio": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_elimina_comparto_senza_dipendenti_collegati(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Da Eliminare")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    db.commit()
    db.refresh(comparto)
    comparto_id = comparto.id

    r = client.post(f"/sedi/comparti/{comparto_id}/elimina", follow_redirects=True)
    assert r.status_code == 200
    db.expire_all()
    assert db.get(SottosezioneCopertura, comparto_id) is None
    assert "flash-ok" in r.text
    assert "eliminato" in r.text.lower()


def test_elimina_comparto_rimette_i_dipendenti_nel_palazzo(client, crea_utente, db):
    """Eliminando il comparto i suoi dipendenti tornano nell'elenco normale
    della sede: si svuota Dipendente.sottosezione, altrimenti resterebbero
    raggruppati sotto un'intestazione che non esiste più, con il minimo di
    copertura ricaduto a 0 in silenzio."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Con Dipendenti")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    dip = Dipendente(cognome="Rimasto", nome="Test", sede_riferimento_id=sede.id, attivo=True, sottosezione="Parcheggio")
    # Anche un disattivato: lasciargli la sottosezione farebbe ricomparire il
    # gruppo fantasma il giorno in cui viene riattivato.
    disattivato = Dipendente(cognome="Disattivato", nome="Test", sede_riferimento_id=sede.id, attivo=False, sottosezione="Parcheggio")
    # Chi sta in un altro comparto della stessa sede non va toccato.
    altro = Dipendente(cognome="Altro", nome="Comparto", sede_riferimento_id=sede.id, attivo=True, sottosezione="Archivio")
    db.add_all([dip, disattivato, altro])
    db.commit()
    db.refresh(comparto)
    comparto_id = comparto.id

    r = client.post(f"/sedi/comparti/{comparto_id}/elimina", follow_redirects=True)
    assert r.status_code == 200
    db.expire_all()
    assert db.get(SottosezioneCopertura, comparto_id) is None
    assert db.get(Dipendente, dip.id).sottosezione is None
    assert db.get(Dipendente, disattivato.id).sottosezione is None
    assert db.get(Dipendente, altro.id).sottosezione == "Archivio"
    assert "sono tornati" in r.text


def test_dopo_aver_eliminato_il_comparto_il_gruppo_sparisce_dal_calendario(client, crea_utente, db):
    """La verifica lato utente: la riga di intestazione del comparto non
    deve più comparire nel calendario della sede."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Comparto Calendario")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    dip = Dipendente(cognome="Parcheggiato", nome="Test", sede_riferimento_id=sede.id, attivo=True, sottosezione="Parcheggio")
    db.add(dip)
    db.commit()
    db.refresh(comparto)

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=8")
    assert "riga-sottosezione" in r.text  # presupposto: prima il gruppo si vede

    client.post(f"/sedi/comparti/{comparto.id}/elimina", follow_redirects=False)
    client.get("/sedi")  # consuma il messaggio di conferma, che cita il nome del comparto

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=8")
    assert r.status_code == 200
    assert "riga-sottosezione" not in r.text
    assert "Parcheggio" not in r.text
    assert "Parcheggiato Test" in r.text  # il dipendente resta, nell'elenco normale


def test_eliminare_comparto_richiede_amministratore(client, crea_utente, db):
    crea_utente("gestore_sedi_test2", "passwordsegreta", "gestore_turni")
    login(client, "gestore_sedi_test2", "passwordsegreta")
    sede = _crea_sede(db, "Sede Gestore Test 2")
    comparto = SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1)
    db.add(comparto)
    db.commit()
    db.refresh(comparto)

    r = client.post(f"/sedi/comparti/{comparto.id}/elimina", follow_redirects=False)
    assert r.status_code == 403
    assert db.get(SottosezioneCopertura, comparto.id) is not None

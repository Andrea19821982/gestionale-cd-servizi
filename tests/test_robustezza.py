from datetime import date, time

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AssegnazioneGiornaliera, Dipendente, Sede, TipoTurno
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
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_modifica_sede_inesistente_da_404(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post("/sedi/9999/modifica", data={"nome": "X", "colore_hex": "#000000"})
    assert r.status_code == 404


def test_modifica_tipo_turno_inesistente_da_404(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/tipi-turno/9999/modifica",
        data={"etichetta": "X", "ora_inizio": "08:00", "ora_fine": "12:00"},
    )
    assert r.status_code == 404


def test_tipo_turno_orario_malformato_da_400(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/tipi-turno/nuovo",
        data={"etichetta": "X", "ora_inizio": "non-un-orario", "ora_fine": "12:00"},
    )
    assert r.status_code == 400


def test_modifica_dipendente_inesistente_da_404(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/dipendenti/9999/modifica",
        data={"cognome": "X", "nome": "Y", "sede_riferimento_id": "", "ordine_visualizzazione": 0},
    )
    assert r.status_code == 404


def test_crea_dipendente_con_sede_inesistente_da_400(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/dipendenti/nuovo",
        data={"cognome": "X", "nome": "Y", "sede_riferimento_id": "9999", "ordine_visualizzazione": 0},
    )
    assert r.status_code == 400


def test_pattern_turno_dipendente_inesistente_da_404(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/dipendenti/9999/pattern",
        data={"turno_settimana_dispari_id": "", "turno_settimana_pari_id": ""},
    )
    assert r.status_code == 404


def test_pattern_turno_id_inesistente_da_400(client, crea_utente, db):
    _login_admin(client, crea_utente)
    dip = Dipendente(cognome="Test", nome="Pattern", attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        f"/dipendenti/{dip.id}/pattern",
        data={"turno_settimana_dispari_id": "9999", "turno_settimana_pari_id": ""},
    )
    assert r.status_code == 400


def test_cella_dipendente_inesistente_da_404(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": 9999, "data": "2026-08-10", "tipo_turno_id": ""},
    )
    assert r.status_code == 404


def test_cella_data_malformata_da_400(client, crea_utente, db):
    _login_admin(client, crea_utente)
    dip = Dipendente(cognome="Test", nome="Data", attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "non-una-data", "tipo_turno_id": ""},
    )
    assert r.status_code == 400


def test_cella_tipo_turno_inesistente_da_400(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Tipo", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-10", "tipo_turno_id": "9999"},
    )
    assert r.status_code == 400


def test_cella_dipendente_senza_sede_da_400(client, crea_utente, db):
    _login_admin(client, crea_utente)
    tipo = _crea_tipo_turno(db)
    dip = Dipendente(cognome="Test", nome="SenzaSede", sede_riferimento_id=None, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-10", "tipo_turno_id": tipo.id},
    )
    assert r.status_code == 400


def test_genera_sede_inesistente_da_404(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post("/calendario/genera", data={"sede_id": 9999, "anno": 2026, "mese": 8})
    assert r.status_code == 404


def test_genera_mese_invalido_da_400(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    r = client.post("/calendario/genera", data={"sede_id": sede.id, "anno": 2026, "mese": 13})
    assert r.status_code == 400


def test_vista_calendario_con_mese_invalido_non_crasha(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.get("/calendario?anno=2026&mese=13")
    assert r.status_code == 200


def test_vista_calendario_con_anno_invalido_non_crasha(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.get("/calendario?anno=99999&mese=1")
    assert r.status_code == 200


def test_vincolo_unicita_assegnazione_dipendente_data(db):
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Unico", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 8, 10), sede_effettiva_id=sede.id, origine="manuale",
    ))
    db.commit()

    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 8, 10), sede_effettiva_id=sede.id, origine="manuale",
    ))
    with pytest.raises(IntegrityError):
        db.commit()


def test_select_cella_ha_attributo_name(client, crea_utente, db):
    """Regressione: senza name="tipo_turno_id" htmx non invia mai il valore
    scelto nella select, e la modifica manuale della cella smette di
    funzionare pur sembrando corretta a un test che chiama l'endpoint
    passando il campo esplicitamente (senza passare da un vero <select>)."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="SelectName", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=8")
    assert r.status_code == 200
    assert 'name="tipo_turno_id"' in r.text


def test_cella_gestisce_corsa_reale_senza_errore(client, crea_utente, db, SessionTest, monkeypatch):
    """Simula la vera corsa: nella finestra tra "controlla se la riga esiste"
    e "inseriscila", un'altra sessione la crea per davvero. Il flush di
    questa richiesta deve quindi urtare il vincolo di unicità reale (non
    simulato), e l'endpoint deve accorgersene e applicare la scelta
    dell'utente come modifica invece di rispondere 500."""
    import app.routers.calendario as calendario_module

    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo_a = _crea_tipo_turno(db, "Turno A")
    tipo_b = _crea_tipo_turno(db, "Turno B")
    dip = Dipendente(cognome="Test", nome="Corsa", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    originale = calendario_module._assegnazione_esistente
    chiamate = {"n": 0}

    def _controllo_con_corsa_simulata(db_arg, dipendente_id, data_obj):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            # Un'altra richiesta "vince la corsa": crea la riga con una
            # sessione indipendente proprio nell'istante in cui questa
            # richiesta ha già controllato che non esistesse ancora.
            sessione_concorrente = SessionTest()
            sessione_concorrente.add(AssegnazioneGiornaliera(
                dipendente_id=dipendente_id, data=data_obj, sede_effettiva_id=sede.id,
                tipo_turno_id=tipo_a.id, origine="manuale",
            ))
            sessione_concorrente.commit()
            sessione_concorrente.close()
            return None
        return originale(db_arg, dipendente_id, data_obj)

    monkeypatch.setattr(calendario_module, "_assegnazione_esistente", _controllo_con_corsa_simulata)

    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-20", "tipo_turno_id": tipo_b.id},
    )
    assert r.status_code == 200

    riga = db.query(AssegnazioneGiornaliera).filter_by(dipendente_id=dip.id, data=date(2026, 8, 20)).first()
    assert riga is not None
    assert riga.tipo_turno_id == tipo_b.id


def test_genera_gestisce_corsa_reale_senza_errore(client, crea_utente, db, SessionTest, monkeypatch):
    """Stessa corsa reale della cella, ma nella generazione massiva da
    pattern: un'altra sessione crea la riga del primo giorno del mese subito
    dopo il controllo "esiste già", cosa che deve far fallire il commit
    finale con un IntegrityError reale, gestito senza rispondere 500."""
    import app.routers.calendario as calendario_module
    from app.models import PatternTurno

    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = _crea_tipo_turno(db)
    dip = Dipendente(cognome="Test", nome="GeneraCorsa", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(PatternTurno(dipendente_id=dip.id, turno_settimana_dispari_id=tipo.id, turno_settimana_pari_id=tipo.id))
    db.commit()

    originale = calendario_module._assegnazione_esistente
    chiamate = {"n": 0}

    def _controllo_con_corsa_simulata(db_arg, dipendente_id, data_obj):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            sessione_concorrente = SessionTest()
            sessione_concorrente.add(AssegnazioneGiornaliera(
                dipendente_id=dipendente_id, data=data_obj, sede_effettiva_id=sede.id,
                tipo_turno_id=tipo.id, origine="pattern",
            ))
            sessione_concorrente.commit()
            sessione_concorrente.close()
            return None
        return originale(db_arg, dipendente_id, data_obj)

    monkeypatch.setattr(calendario_module, "_assegnazione_esistente", _controllo_con_corsa_simulata)

    r = client.post(
        "/calendario/genera",
        data={"sede_id": sede.id, "anno": 2026, "mese": 8},
        follow_redirects=False,
    )
    assert r.status_code == 303

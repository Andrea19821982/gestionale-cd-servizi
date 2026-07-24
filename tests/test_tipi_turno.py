from datetime import date, time

from app.models import AssegnazioneGiornaliera, Dipendente, PatternTurno, Sede, TipoTurno
from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_tt_test", "passwordsegreta", "amministratore")
    login(client, "admin_tt_test", "passwordsegreta")


def _crea_tipo_turno(db, etichetta="Turno Test", inizio=time(7, 0), fine=time(13, 30)):
    tipo = TipoTurno(etichetta=etichetta, ora_inizio=inizio, ora_fine=fine)
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    return tipo


def test_elimina_tipo_turno_non_usato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    tipo = _crea_tipo_turno(db)

    r = client.post(f"/tipi-turno/{tipo.id}/elimina", follow_redirects=False)
    assert r.status_code == 303
    # La route usa una sessione DB separata (Depends(get_db)): l'oggetto è
    # ancora nell'identity map di questa sessione di test, quindi va rimosso
    # esplicitamente prima di verificare che la riga non esista più.
    db.expunge(tipo)
    assert db.query(TipoTurno).filter_by(id=tipo.id).first() is None


def test_non_elimina_tipo_turno_usato_in_assegnazione(client, crea_utente, db):
    _login_admin(client, crea_utente)
    tipo = _crea_tipo_turno(db)
    sede = Sede(nome="Sede TT Test", colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    dip = Dipendente(cognome="TT", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 9, 1), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    r = client.post(f"/tipi-turno/{tipo.id}/elimina", follow_redirects=False)
    assert r.status_code == 303
    # Non cancellato: la riga esiste ancora.
    assert db.get(TipoTurno, tipo.id) is not None


def test_non_elimina_tipo_turno_usato_nel_pattern(client, crea_utente, db):
    _login_admin(client, crea_utente)
    tipo = _crea_tipo_turno(db)
    sede = Sede(nome="Sede TT Pattern", colore_hex="#654321", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    dip = Dipendente(cognome="Pattern", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(PatternTurno(dipendente_id=dip.id, turno_settimana_dispari_id=tipo.id, turno_settimana_pari_id=tipo.id))
    db.commit()

    r = client.post(f"/tipi-turno/{tipo.id}/elimina", follow_redirects=False)
    assert r.status_code == 303
    assert db.get(TipoTurno, tipo.id) is not None


def test_elimina_tipo_turno_richiede_amministratore(client, crea_utente):
    crea_utente("gestore_tt_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_tt_test", "passwordsegreta")

    r = client.post("/tipi-turno/1/elimina", follow_redirects=False)
    assert r.status_code == 403

from app.models import Dipendente, LogModifica
from tests.conftest import login


def test_creazione_sede_genera_log(client, crea_utente, db):
    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    client.post(
        "/sedi/nuova",
        data={"nome": "Sede Loggata", "colore_hex": "#123456"},
        follow_redirects=False,
    )

    log = db.query(LogModifica).filter_by(tabella="sedi", azione="creazione").first()
    assert log is not None
    assert log.utente_id == admin.id
    assert "Sede Loggata" in log.dettaglio
    assert log.timestamp is not None


def test_modifica_dipendente_genera_log(client, crea_utente, db):
    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    db.add(Dipendente(cognome="Loggato", nome="Test", ordine_visualizzazione=0, attivo=True))
    db.commit()
    dipendente = db.query(Dipendente).filter_by(cognome="Loggato").first()

    login(client, "admin_test", "passwordsegreta")
    client.post(
        f"/dipendenti/{dipendente.id}/modifica",
        data={
            "cognome": "Loggato",
            "nome": "Test Modificato",
            "sede_riferimento_id": "",
            "ordine_visualizzazione": 0,
        },
        follow_redirects=False,
    )

    log = db.query(LogModifica).filter_by(
        tabella="dipendenti", record_id=dipendente.id, azione="modifica"
    ).first()
    assert log is not None
    assert log.utente_id == admin.id
    assert "Test Modificato" in log.dettaglio

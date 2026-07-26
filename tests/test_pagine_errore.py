"""Come vengono presentati gli errori a chi usa il programma.

I router sollevano HTTPException con messaggi scritti in italiano semplice,
ma la risposta di default di FastAPI è JSON: su un form POST normale il
browser ci navigava sopra, e l'utente si ritrovava una schermata bianca con
del testo tecnico. Questi test fissano le tre forme della risposta e, cosa
più importante, che il codice di stato non sia cambiato: 90 test altrove si
appoggiano su quello.
"""

from datetime import date

from app.models import Dipendente, Sede
from tests.conftest import login


def _admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def _dipendente(db):
    sede = Sede(nome="Sede Errori", colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    dip = Dipendente(cognome="Errore", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def _assenza_con_date_invertite(client, dip, headers=None):
    return client.post(
        "/assenze/nuova",
        data={
            "dipendente_id": dip.id,
            "data_inizio": "2026-08-20",
            "data_fine": "2026-08-10",  # fine prima dell'inizio
            "tipo_assenza": "Ferie",
        },
        headers=headers or {},
        follow_redirects=False,
    )


def test_il_browser_riceve_una_pagina_con_il_menu_non_del_json(client, crea_utente, db):
    _admin(client, crea_utente)
    dip = _dipendente(db)

    r = _assenza_con_date_invertite(client, dip, headers={"accept": "text/html"})

    assert r.status_code == 400  # il codice non cambia
    assert "text/html" in r.headers["content-type"]
    assert "La data fine non può precedere la data inizio." in r.text
    assert "Torna indietro" in r.text
    assert "🗓️ Calendario" in r.text  # c'è il menu: non è una pagina bianca
    assert '{"detail"' not in r.text


def test_htmx_riceve_solo_il_testo_da_mostrare_nel_banner(client, crea_utente, db):
    _admin(client, crea_utente)
    dip = _dipendente(db)

    r = _assenza_con_date_invertite(client, dip, headers={"HX-Request": "true"})

    assert r.status_code == 400
    assert r.text.strip() == "La data fine non può precedere la data inizio."
    assert "<html" not in r.text.lower()  # niente pagina intera dentro un frammento


def test_le_altre_richieste_ricevono_ancora_il_json_di_sempre(client, crea_utente, db):
    """Il comportamento storico resta per tutto ciò che non è né htmx né una
    navigazione del browser."""
    _admin(client, crea_utente)
    dip = _dipendente(db)

    r = _assenza_con_date_invertite(client, dip, headers={"accept": "application/json"})

    assert r.status_code == 400
    assert r.json()["detail"] == "La data fine non può precedere la data inizio."


def test_403_e_404_mostrano_un_titolo_comprensibile(client, crea_utente, db):
    crea_utente("sola_lettura", "passwordsegreta", "consultazione")
    login(client, "sola_lettura", "passwordsegreta")

    vietato = client.get("/report", headers={"accept": "text/html"}, follow_redirects=False)
    assert vietato.status_code == 403
    assert "Non hai i permessi" in vietato.text

    inesistente = client.get(
        "/dipendenti/999999/storico", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert inesistente.status_code == 404
    assert "non trovato" in inesistente.text.lower()


def test_la_pagina_di_errore_non_espone_dettagli_tecnici(client, crea_utente, db):
    """Il messaggio è quello scritto per l'utente, senza traceback né nomi di
    file: la pagina la vede chi non è tecnico."""
    _admin(client, crea_utente)
    dip = _dipendente(db)

    r = _assenza_con_date_invertite(client, dip, headers={"accept": "text/html"})

    for tecnicismo in ("Traceback", "app/routers", "HTTPException", "sqlalchemy"):
        assert tecnicismo not in r.text

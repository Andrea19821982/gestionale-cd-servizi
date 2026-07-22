from datetime import date, timedelta

from app.models import EventoSala, Sala, Sede
from tests.conftest import login


def _crea_sede(db, nome="Montecitorio Test", copertura_minima_ordinaria=0):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True, copertura_minima_ordinaria=copertura_minima_ordinaria)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def test_gestore_turni_non_puo_creare_sala(client, crea_utente, db):
    sede = _crea_sede(db)
    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")
    r = client.post(
        "/sale/nuova",
        data={"nome": "Sala Test", "sede_id": sede.id, "copertura_minima_aggiuntiva": 1},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_admin_crea_e_modifica_sala(client, crea_utente, db):
    sede = _crea_sede(db)
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    r = client.post(
        "/sale/nuova",
        data={"nome": "Sala della Lupa Test", "sede_id": sede.id, "copertura_minima_aggiuntiva": 2},
        follow_redirects=False,
    )
    assert r.status_code == 303
    sala = db.query(Sala).filter_by(nome="Sala della Lupa Test").first()
    assert sala is not None
    assert sala.copertura_minima_aggiuntiva == 2

    r2 = client.post(
        f"/sale/{sala.id}/modifica",
        data={"nome": "Sala della Lupa Modificata", "sede_id": sede.id, "copertura_minima_aggiuntiva": 3},
        # niente "attivo" -> deve diventare False
        follow_redirects=False,
    )
    assert r2.status_code == 303
    db.expire_all()
    sala_aggiornata = db.query(Sala).filter_by(id=sala.id).first()
    assert sala_aggiornata.nome == "Sala della Lupa Modificata"
    assert sala_aggiornata.copertura_minima_aggiuntiva == 3
    assert sala_aggiornata.attivo is False


def test_copertura_aggiuntiva_negativa_rifiutata(client, crea_utente, db):
    sede = _crea_sede(db)
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    r = client.post(
        "/sale/nuova",
        data={"nome": "Sala Negativa", "sede_id": sede.id, "copertura_minima_aggiuntiva": -1},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_gestore_turni_puo_creare_ed_eliminare_evento(client, crea_utente, db):
    sede = _crea_sede(db)
    sala = Sala(nome="Sala Evento Test", sede_id=sede.id, copertura_minima_aggiuntiva=2, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)

    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")

    oggi = date.today()
    domani = oggi + timedelta(days=1)
    r = client.post(
        "/sale/eventi/nuovo",
        data={
            "sala_id": sala.id,
            "data_inizio": oggi.isoformat(),
            "data_fine": domani.isoformat(),
            "descrizione": "Seduta di prova",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    evento = db.query(EventoSala).filter_by(sala_id=sala.id).first()
    assert evento is not None
    assert evento.descrizione == "Seduta di prova"

    evento_id = evento.id
    r2 = client.post(f"/sale/eventi/{evento_id}/elimina", follow_redirects=False)
    assert r2.status_code == 303
    db.expire_all()
    assert db.query(EventoSala).filter_by(id=evento_id).first() is None


def test_evento_con_data_fine_precedente_rifiutato(client, crea_utente, db):
    sede = _crea_sede(db)
    sala = Sala(nome="Sala Date Invertite", sede_id=sede.id, copertura_minima_aggiuntiva=1, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    oggi = date.today()
    ieri = oggi - timedelta(days=1)
    r = client.post(
        "/sale/eventi/nuovo",
        data={"sala_id": sala.id, "data_inizio": oggi.isoformat(), "data_fine": ieri.isoformat()},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_consultazione_non_puo_creare_evento(client, crea_utente, db):
    sede = _crea_sede(db)
    sala = Sala(nome="Sala Sola Lettura", sede_id=sede.id, copertura_minima_aggiuntiva=1, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)

    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.post(
        "/sale/eventi/nuovo",
        data={"sala_id": sala.id, "data_inizio": date.today().isoformat(), "data_fine": date.today().isoformat()},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_evento_ricorrente_crea_una_occorrenza_a_settimana(client, crea_utente, db):
    sede = _crea_sede(db)
    sala = Sala(nome="Sala Ricorrente Test", sede_id=sede.id, copertura_minima_aggiuntiva=1, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)

    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")

    oggi = date.today()
    fine_ricorrenza = oggi + timedelta(days=21)  # 3 settimane -> attesa: oggi + 3 occorrenze successive
    r = client.post(
        "/sale/eventi/nuovo",
        data={
            "sala_id": sala.id,
            "data_inizio": oggi.isoformat(),
            "data_fine": oggi.isoformat(),
            "descrizione": "Seduta ricorrente",
            "ripeti_fino_al": fine_ricorrenza.isoformat(),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    eventi = db.query(EventoSala).filter_by(sala_id=sala.id).order_by(EventoSala.data_inizio).all()
    assert len(eventi) == 4  # oggi + 3 settimane successive incluse
    date_attese = [oggi + timedelta(days=7 * n) for n in range(4)]
    assert [e.data_inizio for e in eventi] == date_attese
    assert all(e.descrizione == "Seduta ricorrente" for e in eventi)


def test_evento_ricorrente_con_troppe_occorrenze_rifiutato(client, crea_utente, db):
    sede = _crea_sede(db)
    sala = Sala(nome="Sala Ricorrente Lunga", sede_id=sede.id, copertura_minima_aggiuntiva=1, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    oggi = date.today()
    fine_ricorrenza = oggi + timedelta(weeks=60)  # oltre il limite di sicurezza (52)
    r = client.post(
        "/sale/eventi/nuovo",
        data={
            "sala_id": sala.id,
            "data_inizio": oggi.isoformat(),
            "data_fine": oggi.isoformat(),
            "ripeti_fino_al": fine_ricorrenza.isoformat(),
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert db.query(EventoSala).filter_by(sala_id=sala.id).count() == 0


def test_pagina_sale_elenca_sale_ed_eventi(client, crea_utente, db):
    sede = _crea_sede(db)
    sala = Sala(nome="Sala Elenco Test", sede_id=sede.id, copertura_minima_aggiuntiva=1, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    db.add(EventoSala(sala_id=sala.id, data_inizio=date.today(), data_fine=date.today(), descrizione="Evento visibile"))
    db.commit()

    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/sale")
    assert r.status_code == 200
    assert "Sala Elenco Test" in r.text
    assert "Evento visibile" in r.text

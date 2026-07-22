from datetime import date, time, timedelta

from app.models import AssegnazioneGiornaliera, Dipendente, EventoSala, Sala, Sede, TipoTurno
from app.routers.copertura import calcola_copertura
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_copertura_distingue_presente_assente_non_pianificato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = TipoTurno(etichetta="Mattina Cop", ora_inizio=time(7, 0), ora_fine=time(13, 30))
    db.add(tipo)
    db.commit()
    db.refresh(tipo)

    presente = Dipendente(cognome="Presente", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    assente = Dipendente(cognome="Assente", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    non_pianificato = Dipendente(cognome="NonPianificato", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([presente, assente, non_pianificato])
    db.commit()
    for d in (presente, assente, non_pianificato):
        db.refresh(d)

    oggi = date(2026, 8, 10)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=presente.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.add(AssegnazioneGiornaliera(
        dipendente_id=assente.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=None, origine="assenza",
    ))
    db.commit()

    r = client.get(f"/copertura?data={oggi.isoformat()}")
    assert r.status_code == 200
    testo = r.text
    riga_presente = testo.split("Presente Test")[1].split("</tr>")[0]
    riga_assente = testo.split("Assente Test")[1].split("</tr>")[0]
    riga_non_pianificato = testo.split("NonPianificato Test")[1].split("</tr>")[0]
    assert "Presente</span>" in riga_presente
    assert "Assente</span>" in riga_assente
    assert "Non pianificato</span>" in riga_non_pianificato
    assert "1 presenti su 3" in testo


def test_copertura_richiede_login(client):
    r = client.get("/copertura", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_copertura_accessibile_a_consultazione(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/copertura")
    assert r.status_code == 200


def test_copertura_minima_zero_senza_configurazione(db):
    _crea_sede(db)
    oggi = date.today()
    blocchi = calcola_copertura(db, oggi)
    assert blocchi[0]["copertura_minima"] == 0
    assert blocchi[0]["sotto_minimo"] is False


def test_copertura_minima_ordinaria_segnala_carenza(db):
    sede = _crea_sede(db)
    sede.copertura_minima_ordinaria = 2
    db.commit()
    oggi = date.today()
    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["copertura_minima"] == 2
    assert blocco["presenti"] == 0
    assert blocco["sotto_minimo"] is True


def test_evento_in_sala_aumenta_copertura_minima(db):
    sede = _crea_sede(db)
    sede.copertura_minima_ordinaria = 1
    db.commit()
    sala = Sala(nome="Sala della Lupa Test", sede_id=sede.id, copertura_minima_aggiuntiva=3, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    oggi = date.today()
    db.add(EventoSala(sala_id=sala.id, data_inizio=oggi, data_fine=oggi, descrizione="Seduta"))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["copertura_minima"] == 4  # 1 ordinaria + 3 per l'evento
    assert len(blocco["eventi_oggi"]) == 1
    assert blocco["eventi_oggi"][0].sala_id == sala.id
    assert blocco["sotto_minimo"] is True


def test_evento_fuori_data_non_conta(db):
    sede = _crea_sede(db)
    sede.copertura_minima_ordinaria = 1
    db.commit()
    sala = Sala(nome="Sala Fuori Data", sede_id=sede.id, copertura_minima_aggiuntiva=5, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    oggi = date.today()
    db.add(EventoSala(sala_id=sala.id, data_inizio=oggi + timedelta(days=5), data_fine=oggi + timedelta(days=6)))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    assert blocchi[0]["copertura_minima"] == 1
    assert blocchi[0]["eventi_oggi"] == []


def test_sala_disattivata_non_conta_anche_con_evento_attivo(db):
    sede = _crea_sede(db)
    sede.copertura_minima_ordinaria = 1
    db.commit()
    sala = Sala(nome="Sala Disattivata", sede_id=sede.id, copertura_minima_aggiuntiva=5, attivo=False)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    oggi = date.today()
    db.add(EventoSala(sala_id=sala.id, data_inizio=oggi, data_fine=oggi))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    assert blocchi[0]["copertura_minima"] == 1
    assert blocchi[0]["eventi_oggi"] == []


def test_presenti_sufficienti_non_segnalano_carenza(db):
    sede = _crea_sede(db)
    sede.copertura_minima_ordinaria = 1
    db.commit()
    tipo = TipoTurno(etichetta="Mattina Copertura Test", ora_inizio=time(7, 0), ora_fine=time(13, 30))
    db.add(tipo)
    dip = Dipendente(cognome="Bianchi", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.refresh(tipo)
    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["presenti"] == 1
    assert blocco["copertura_minima"] == 1
    assert blocco["sotto_minimo"] is False


def test_suggerisce_dipendenti_non_pianificati_in_altre_sedi(db):
    sede_carente = _crea_sede(db, nome="Sede Carente")
    sede_carente.copertura_minima_ordinaria = 2
    sede_altra = _crea_sede(db, nome="Sede Altra")
    db.commit()

    libero_altrove = Dipendente(cognome="Libero", nome="Altrove", sede_riferimento_id=sede_altra.id, attivo=True)
    libero_qui = Dipendente(cognome="Libero", nome="Qui", sede_riferimento_id=sede_carente.id, attivo=True)
    db.add_all([libero_altrove, libero_qui])
    db.commit()

    oggi = date.today()
    blocchi = calcola_copertura(db, oggi)
    blocco_carente = next(b for b in blocchi if b["sede"].id == sede_carente.id)
    blocco_altro = next(b for b in blocchi if b["sede"].id == sede_altra.id)

    assert blocco_carente["sotto_minimo"] is True
    suggeriti_id = {dip.id for dip in blocco_carente["dipendenti_suggeriti"]}
    assert libero_altrove.id in suggeriti_id
    # Un dipendente non pianificato nella STESSA sede carente non è un
    # suggerimento utile (non è una risorsa "libera altrove").
    assert libero_qui.id not in suggeriti_id
    # Un blocco che rispetta il minimo non propone suggerimenti.
    assert blocco_altro["dipendenti_suggeriti"] == []

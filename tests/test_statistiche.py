import re
from datetime import date, time

from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Sede, TipoTurno
from tests.conftest import login


def _testo_cella(frammento_cella: str) -> str:
    """Testo visibile di un frammento ' attributi...>contenuto' ottenuto
    tagliando su "<td" (quindi senza il "<td" iniziale, ma con il resto
    dell'apertura del tag fino al primo ">"): rimuove sia il resto
    dell'apertura del tag sia eventuali tag annidati (es. <span> per i
    badge), così i test non dipendono dal markup esatto della cella."""
    senza_apertura_tag = re.sub(r"^[^>]*>", "", frammento_cella)
    return re.sub(r"<[^>]+>", "", senza_apertura_tag).strip()


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _crea_tipo_turno(db, etichetta, ora_inizio, ora_fine):
    tipo = TipoTurno(etichetta=etichetta, ora_inizio=ora_inizio, ora_fine=ora_fine)
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    return tipo


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_ferie_residue_calcolate_correttamente(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Ferie", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    assert dip.giorni_ferie_annuali == 26

    db.add(Assenza(
        dipendente_id=dip.id, data_inizio=date(2026, 8, 1), data_fine=date(2026, 8, 5),
        tipo_assenza="Ferie", stato="approvata",
    ))
    db.commit()

    r = client.get("/statistiche?anno=2026&mese=8")
    assert r.status_code == 200
    testo = r.text
    assert "Ferie Test" in testo
    # 5 giorni usati, 21 residui (26 - 5)
    riga = testo.split("Ferie Test")[1].split("</tr>")[0]
    assert ">5<" in riga
    assert ">21.0<" in riga  # 26.0 (ferie effettive a tempo pieno) - 5


def test_ferie_residue_clip_sull_anno(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Cavallo", nome="Anno", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    # 30-31 dic 2025 + 1-2 gen 2026 = 4 giorni totali, 2 in ciascun anno.
    db.add(Assenza(
        dipendente_id=dip.id, data_inizio=date(2025, 12, 30), data_fine=date(2026, 1, 2),
        tipo_assenza="Ferie", stato="approvata",
    ))
    db.commit()

    r_2025 = client.get("/statistiche?anno=2025&mese=12")
    riga_2025 = r_2025.text.split("Cavallo Anno")[1].split("</tr>")[0]
    assert ">2<" in riga_2025

    r_2026 = client.get("/statistiche?anno=2026&mese=1")
    riga_2026 = r_2026.text.split("Cavallo Anno")[1].split("</tr>")[0]
    assert ">2<" in riga_2026


def test_ore_lavorate_calcolate_dalle_assegnazioni(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = _crea_tipo_turno(db, "Mattina Stat", time(7, 0), time(13, 30))  # 6.5 ore
    dip = Dipendente(cognome="Ore", nome="Lavorate", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    for giorno in (10, 11, 12):
        db.add(AssegnazioneGiornaliera(
            dipendente_id=dip.id, data=date(2026, 8, giorno), sede_effettiva_id=sede.id,
            tipo_turno_id=tipo.id, origine="manuale",
        ))
    # Un giorno di assenza nello stesso mese non deve contare come ore lavorate.
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 8, 13), sede_effettiva_id=sede.id,
        tipo_turno_id=None, origine="assenza",
    ))
    db.commit()

    r = client.get("/statistiche?anno=2026&mese=8")
    riga = r.text.split("Ore Lavorate")[1].split("</tr>")[0]
    assert ">19.5<" in riga  # 3 giorni * 6.5 ore


def test_statistiche_richiede_login(client):
    r = client.get("/statistiche", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_statistiche_accessibile_a_consultazione(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/statistiche")
    assert r.status_code == 200


def test_statistiche_mostra_assenze_concesse_e_rifiutate(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Esiti", nome="Assenze", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    db.add_all([
        Assenza(dipendente_id=dip.id, data_inizio=date(2026, 3, 1), data_fine=date(2026, 3, 2),
                tipo_assenza="Ferie", stato="approvata"),
        Assenza(dipendente_id=dip.id, data_inizio=date(2026, 4, 1), data_fine=date(2026, 4, 2),
                tipo_assenza="Permesso", stato="rifiutata"),
        Assenza(dipendente_id=dip.id, data_inizio=date(2026, 5, 1), data_fine=date(2026, 5, 2),
                tipo_assenza="Permesso", stato="rifiutata"),
    ])
    db.commit()

    r = client.get("/statistiche?anno=2026&mese=8")
    riga = r.text.split("Esiti Assenze")[1].split("</tr>")[0]
    celle = [_testo_cella(c.split("</td")[0]) for c in riga.split("<td")[1:]]
    # ordine colonne: dipendente, sede, ferie annuali, usate, residue, ore, ore contrattuali, sostituzioni, concesse, rifiutate
    assert celle[-2] == "1"  # concesse
    assert celle[-1] == "2"  # rifiutate


def test_ferie_annuali_prorate_per_part_time(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(
        cognome="Parziale", nome="Tempo", sede_riferimento_id=sede.id, attivo=True,
        giorni_ferie_annuali=26, ore_settimanali_contrattuali=20.0,
    )
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get("/statistiche?anno=2026&mese=8")
    riga = r.text.split("Parziale Tempo")[1].split("</tr>")[0]
    # part-time al 50% (20/40 ore): ferie annuali prorate a 13.0 giorni
    assert ">13.0<" in riga


def test_selettore_mese_mostra_nomi_non_numeri(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.get("/statistiche?anno=2026&mese=8")
    assert r.status_code == 200
    assert "Agosto" in r.text
    assert 'value="8" selected' in r.text


def test_ore_contrattuali_mese_riflette_il_part_time(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(
        cognome="OreContratto", nome="Test", sede_riferimento_id=sede.id, attivo=True,
        ore_settimanali_contrattuali=20.0,
    )
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get("/statistiche?anno=2026&mese=8")
    riga = r.text.split("OreContratto Test")[1].split("</tr>")[0]
    assert ">87.0<" in riga  # 20 ore/settimana * 4.348 settimane/mese

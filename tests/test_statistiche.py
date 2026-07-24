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


def test_valori_corretti_e_isolati_con_piu_dipendenti(client, crea_utente, db):
    """Caratterizza il fix dell'N+1 in statistiche(): con più dipendenti in
    pagina, ciascuno deve mostrare SOLO i propri numeri (ferie usate, ore
    lavorate, sostituzioni, esiti assenze), senza che il batching per id
    faccia trapelare i dati di un dipendente su un altro. Copre anche i due
    casi limite tipici di un bug di raggruppamento: un dipendente senza
    alcuna assegnazione/assenza nel periodo (tutto a zero) e un dipendente
    con dati solo fuori dal mese/anno interrogato (deve restare a zero per
    quel periodo, pur avendo righe nel database)."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = _crea_tipo_turno(db, "Mattina Multi", time(7, 0), time(13, 30))  # 6.5 ore

    # Dipendente A: dati pieni nel periodo interrogato (agosto 2026 / anno 2026).
    dip_a = Dipendente(cognome="Multi", nome="Alfa", sede_riferimento_id=sede.id, attivo=True)
    # Dipendente B: nessuna assegnazione né assenza in assoluto (tutto zero).
    dip_b = Dipendente(cognome="Multi", nome="Beta", sede_riferimento_id=sede.id, attivo=True)
    # Dipendente C: ha dati, ma solo fuori dal mese/anno richiesto (es. "assunto"
    # più avanti nell'anno / assegnazioni in un mese diverso): per agosto 2026
    # deve risultare a zero ore lavorate, pur avendo assegnazioni a luglio.
    dip_c = Dipendente(cognome="Multi", nome="Gamma", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([dip_a, dip_b, dip_c])
    db.commit()
    for d in (dip_a, dip_b, dip_c):
        db.refresh(d)

    # A: 2 giorni lavorati ad agosto 2026, 3 giorni di ferie approvate nel 2026,
    # 2 assenze concesse (la ferie stessa + un permesso) e 1 rifiutata nel 2026.
    for giorno in (10, 11):
        db.add(AssegnazioneGiornaliera(
            dipendente_id=dip_a.id, data=date(2026, 8, giorno), sede_effettiva_id=sede.id,
            tipo_turno_id=tipo.id, origine="manuale",
        ))
    db.add(Assenza(
        dipendente_id=dip_a.id, data_inizio=date(2026, 6, 1), data_fine=date(2026, 6, 3),
        tipo_assenza="Ferie", stato="approvata",
    ))
    db.add(Assenza(
        dipendente_id=dip_a.id, data_inizio=date(2026, 5, 1), data_fine=date(2026, 5, 1),
        tipo_assenza="Permesso", stato="approvata",
    ))
    db.add(Assenza(
        dipendente_id=dip_a.id, data_inizio=date(2026, 4, 1), data_fine=date(2026, 4, 1),
        tipo_assenza="Permesso", stato="rifiutata",
    ))

    # C: assegnazioni SOLO a luglio 2026 (fuori dal mese richiesto, agosto) e
    # ferie approvate SOLO nel 2025 (fuori dall'anno richiesto, 2026).
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip_c.id, data=date(2026, 7, 15), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.add(Assenza(
        dipendente_id=dip_c.id, data_inizio=date(2025, 8, 1), data_fine=date(2025, 8, 2),
        tipo_assenza="Ferie", stato="approvata",
    ))
    db.commit()

    r = client.get("/statistiche?anno=2026&mese=8")
    assert r.status_code == 200

    # Nota: split(nome)[1] taglia via il primo <td> (quello col nome), quindi
    # split("<td") su questo resto parte già dalla cella "sede" in poi: si usano
    # indici negativi (stabili, contati dalla fine della riga) invece che
    # positivi, per non doversi ricordare di questo slittamento di uno.
    # ordine dalla fine: ..., usate(-7), residue(-6), ore(-5), ore contr.(-4), sostituzioni(-3), concesse(-2), rifiutate(-1)
    riga_a = r.text.split("Multi Alfa")[1].split("</tr>")[0]
    celle_a = [_testo_cella(c.split("</td")[0]) for c in riga_a.split("<td")[1:]]
    assert celle_a[-7] == "3"  # ferie usate (solo le sue, non quelle di altri)
    assert celle_a[-5] == "13.0"  # ore lavorate: 2 giorni * 6.5 ore
    assert celle_a[-2] == "2"  # concesse: ferie di giugno + permesso di maggio, entrambi approvati
    assert celle_a[-1] == "1"  # rifiutate

    riga_b = r.text.split("Multi Beta")[1].split("</tr>")[0]
    celle_b = [_testo_cella(c.split("</td")[0]) for c in riga_b.split("<td")[1:]]
    assert celle_b[-7] == "0"  # ferie usate: nessuna assenza in assoluto
    assert celle_b[-5] == "0.0"  # ore lavorate: nessuna assegnazione in assoluto
    assert celle_b[-3] == "0"  # sostituzioni fatte
    assert celle_b[-2] == "0"  # concesse
    assert celle_b[-1] == "0"  # rifiutate

    riga_c = r.text.split("Multi Gamma")[1].split("</tr>")[0]
    celle_c = [_testo_cella(c.split("</td")[0]) for c in riga_c.split("<td")[1:]]
    assert celle_c[-7] == "0"  # ferie usate nel 2026: la sua ferie è del 2025
    assert celle_c[-5] == "0.0"  # ore lavorate ad agosto: la sua assegnazione è a luglio

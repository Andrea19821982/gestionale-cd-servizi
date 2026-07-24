from datetime import date, time

from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Sede, TipoTurno
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


def test_costo_del_lavoro_calcolato_da_ore_e_costo_orario(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = TipoTurno(etichetta="Mattina Report", ora_inizio=time(7, 0), ora_fine=time(13, 30))  # 6.5 ore
    db.add(tipo)
    db.commit()
    db.refresh(tipo)

    dip = Dipendente(
        cognome="Costo", nome="Test", sede_riferimento_id=sede.id, attivo=True, costo_orario=10.0,
    )
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 8, 10), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    r = client.get("/report?anno=2026&mese=8")
    assert r.status_code == 200
    riga = r.text.split("Costo Test")[1].split("</tr>")[0]
    assert "65.00" in riga  # 6.5 ore * 10€/ora


def test_dipendente_senza_costo_orario_non_entra_nel_totale(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="SenzaCosto", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get("/report?anno=2026&mese=8")
    riga = r.text.split("SenzaCosto Test")[1].split("</tr>")[0]
    assert ">—<" in riga


def test_dipendente_con_costo_orario_zero_mostra_zero_non_trattino(client, crea_utente, db):
    """Prima del fix, `if dip.costo_orario` trattava 0.0 come "non impostato"
    (0 è falsy in Python) e mostrava "—" invece di "0.00 €": un dipendente
    con costo orario esplicitamente a zero (es. volontario) va distinto da
    uno senza costo impostato."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="CostoZero", nome="Test", sede_riferimento_id=sede.id, attivo=True, costo_orario=0.0)
    db.add(dip)
    db.commit()

    r = client.get("/report?anno=2026&mese=8")
    riga = r.text.split("CostoZero Test")[1].split("</tr>")[0]
    assert ">—<" not in riga
    assert "0.00" in riga


def test_andamento_assenteismo_conta_solo_assenze_approvate(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Assenteismo", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add_all([
        Assenza(dipendente_id=dip.id, data_inizio=date(2026, 3, 1), data_fine=date(2026, 3, 3),
                tipo_assenza="Ferie", stato="approvata"),
        Assenza(dipendente_id=dip.id, data_inizio=date(2026, 3, 10), data_fine=date(2026, 3, 12),
                tipo_assenza="Ferie", stato="richiesta"),
    ])
    db.commit()

    r = client.get("/report?anno=2026")
    # Isola la tabella "Andamento assenteismo": il mini grafico a barre
    # sopra la tabella ripete il nome del mese anche nel tooltip di ogni
    # barra, quindi cercare "Marzo" nella pagina intera troverebbe prima
    # quello e non la riga della tabella che questo test vuole verificare.
    tabella = r.text.split("<thead><tr><th>Mese</th>")[1]
    riga_marzo = tabella.split("Marzo")[1].split("</tr>")[0]
    assert ">3<" in riga_marzo  # solo i 3 giorni approvati, non i 3 in attesa


def test_report_richiede_ruolo_operativo(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/report", follow_redirects=False)
    assert r.status_code == 403


def test_andamento_assenteismo_clippa_correttamente_a_cavallo_di_due_mesi(client, crea_utente, db):
    """Caratterizza il fix dell'N+1 in _giorni_assenza_azienda_nel_mese
    (chiamata una volta per ciascuno dei 12 mesi): un'assenza che attraversa
    il confine tra due mesi deve contribuire solo con i giorni che cadono in
    ciascun mese (clip), e un mese senza nessuna assenza deve restare a 0,
    non sparire o sollevare un errore."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Cavallo", nome="Mese", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    # 30-31 gennaio + 1-2 febbraio 2026 = 4 giorni totali, 2 in gennaio e 2 in febbraio.
    db.add(Assenza(
        dipendente_id=dip.id, data_inizio=date(2026, 1, 30), data_fine=date(2026, 2, 2),
        tipo_assenza="Malattia", stato="approvata",
    ))
    db.commit()

    r = client.get("/report?anno=2026")
    tabella = r.text.split("<thead><tr><th>Mese</th>")[1]
    riga_gennaio = tabella.split("Gennaio")[1].split("</tr>")[0]
    riga_febbraio = tabella.split("Febbraio")[1].split("</tr>")[0]
    riga_marzo = tabella.split("Marzo")[1].split("</tr>")[0]
    assert ">2<" in riga_gennaio
    assert ">2<" in riga_febbraio
    assert ">0<" in riga_marzo  # nessuna assenza a marzo: deve restare a zero, non sparire


def test_costo_del_lavoro_isolato_tra_piu_dipendenti(client, crea_utente, db):
    """Con più dipendenti, il batching delle ore lavorate per il costo del
    lavoro non deve mescolare i minuti di uno con quelli di un altro: un
    dipendente senza assegnazioni nel mese richiesto deve restare a 0 ore
    anche se ha assegnazioni in un mese diverso, e uno con assegnazioni deve
    vedere solo le proprie."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = TipoTurno(etichetta="Mattina Report Multi", ora_inizio=time(7, 0), ora_fine=time(13, 30))  # 6.5 ore
    db.add(tipo)
    db.commit()
    db.refresh(tipo)

    dip_pieno = Dipendente(
        cognome="CostoMulti", nome="Pieno", sede_riferimento_id=sede.id, attivo=True, costo_orario=20.0,
    )
    dip_altro_mese = Dipendente(
        cognome="CostoMulti", nome="AltroMese", sede_riferimento_id=sede.id, attivo=True, costo_orario=20.0,
    )
    db.add_all([dip_pieno, dip_altro_mese])
    db.commit()
    for d in (dip_pieno, dip_altro_mese):
        db.refresh(d)

    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip_pieno.id, data=date(2026, 8, 10), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    # Assegnazione fuori dal mese richiesto (luglio invece di agosto): non deve
    # contribuire alle ore di agosto di questo dipendente.
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip_altro_mese.id, data=date(2026, 7, 10), sede_effettiva_id=sede.id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    r = client.get("/report?anno=2026&mese=8")
    riga_pieno = r.text.split("CostoMulti Pieno")[1].split("</tr>")[0]
    riga_altro = r.text.split("CostoMulti AltroMese")[1].split("</tr>")[0]
    assert "130.00" in riga_pieno  # 6.5 ore * 20€/ora
    assert "0.00" in riga_altro  # nessuna assegnazione ad agosto per questo dipendente

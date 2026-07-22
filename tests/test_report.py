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
    testo = r.text
    riga_marzo = testo.split("Marzo")[1].split("</tr>")[0]
    assert ">3<" in riga_marzo  # solo i 3 giorni approvati, non i 3 in attesa


def test_report_richiede_ruolo_operativo(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/report", follow_redirects=False)
    assert r.status_code == 403

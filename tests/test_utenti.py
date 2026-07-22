from datetime import date, timedelta

from app.auth import verify_password
from app.models import DelegaApprovazione, Dipendente, Sede, Utente
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    admin = crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    return admin


def test_amministratore_crea_utente_collegato_a_dipendente(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Collegato", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/utenti/nuovo",
        data={
            "username": "nuovo_dipendente",
            "password": "passwordsegreta",
            "ruolo": "dipendente",
            "dipendente_collegato_id": dip.id,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    creato = db.query(Utente).filter_by(username="nuovo_dipendente").first()
    assert creato is not None
    assert creato.ruolo == "dipendente"
    assert creato.dipendente_collegato_id == dip.id


def test_username_duplicato_viene_rifiutato(client, crea_utente):
    _login_admin(client, crea_utente)
    crea_utente("esistente", "passwordsegreta", "consultazione")

    r = client.post(
        "/utenti/nuovo",
        data={"username": "esistente", "password": "passwordsegreta", "ruolo": "consultazione"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_modifica_utente_cambia_ruolo_e_password(client, crea_utente, db):
    _login_admin(client, crea_utente)
    utente = crea_utente("da_modificare", "vecchiapassword", "consultazione")

    r = client.post(
        f"/utenti/{utente.id}/modifica",
        data={"ruolo": "gestore_turni", "attivo": "on", "nuova_password": "nuovapassword"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.refresh(utente)
    assert utente.ruolo == "gestore_turni"
    assert verify_password("nuovapassword", utente.password_hash)


def test_elenco_utenti_richiede_amministratore(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/utenti", follow_redirects=False)
    assert r.status_code == 403


def test_amministratore_non_puo_disattivare_se_stesso(client, crea_utente):
    admin = _login_admin(client, crea_utente)
    r = client.post(
        f"/utenti/{admin.id}/modifica",
        data={"ruolo": "amministratore"},  # niente "attivo" -> checkbox_a_bool restituisce False
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_amministratore_non_puo_degradare_se_stesso(client, crea_utente):
    admin = _login_admin(client, crea_utente)
    r = client.post(
        f"/utenti/{admin.id}/modifica",
        data={"ruolo": "gestore_turni", "attivo": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_amministratore_puo_modificare_un_altro_amministratore(client, crea_utente, db):
    _login_admin(client, crea_utente)
    altro_admin = crea_utente("altro_admin", "passwordsegreta", "amministratore")
    r = client.post(
        f"/utenti/{altro_admin.id}/modifica",
        data={"ruolo": "gestore_turni", "attivo": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.refresh(altro_admin)
    assert altro_admin.ruolo == "gestore_turni"


def _crea_delega(db, delegato, giorni_da_oggi_inizio, giorni_da_oggi_fine):
    delega = DelegaApprovazione(
        utente_delegato_id=delegato.id,
        data_inizio=date.today() + timedelta(days=giorni_da_oggi_inizio),
        data_fine=date.today() + timedelta(days=giorni_da_oggi_fine),
    )
    db.add(delega)
    db.commit()
    db.refresh(delega)
    return delega


def test_deleghe_scadute_nascoste_di_default(client, crea_utente, db):
    _login_admin(client, crea_utente)
    delegato = crea_utente("delegato_test", "passwordsegreta", "gestore_turni")
    _crea_delega(db, delegato, -10, -5)  # scaduta
    _crea_delega(db, delegato, 0, 5)  # attiva

    r = client.get("/utenti")
    assert r.text.count("delegato_test") >= 1
    # Nella tabella delle deleghe non deve comparire la riga scaduta: verifica
    # tramite il conteggio dei pulsanti "Revoca" (">Revoca<" per non contare
    # anche il testo del confirm() JS "Revocare questa delega?").
    r_tutte = client.get("/utenti?tutte_le_deleghe=1")
    assert r_tutte.text.count(">Revoca<") == 2
    assert r.text.count(">Revoca<") == 1


def test_deleghe_tutte_le_deleghe_mostra_anche_le_scadute(client, crea_utente, db):
    _login_admin(client, crea_utente)
    delegato = crea_utente("delegato_test2", "passwordsegreta", "gestore_turni")
    _crea_delega(db, delegato, -10, -5)

    r = client.get("/utenti?tutte_le_deleghe=1")
    assert "Scaduta" in r.text

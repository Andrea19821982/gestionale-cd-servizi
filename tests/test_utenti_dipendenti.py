"""Preparazione degli accessi per i dipendenti.

Il ruolo "dipendente" esisteva già; quello che mancava era il modo di
darne uno a un gruppo di persone senza doversi ricordare a memoria chi si
era già fatto e ricercarlo ogni volta nella tendina di tutti.
"""

from app.models import Dipendente, Sede, Utente
from app.routers.utenti import _username_libero
from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_accessi", "passwordsegreta", "amministratore")
    login(client, "admin_accessi", "passwordsegreta")


def _dipendente(db, cognome, nome="Test", sede=None):
    dip = Dipendente(cognome=cognome, nome=nome, attivo=True,
                     sede_riferimento_id=sede.id if sede else None)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def test_username_proposto_dal_cognome_e_nome(db):
    dip = _dipendente(db, "Rossi", "Mario")
    assert _username_libero(db, dip) == "rossi.mario"


def test_username_proposto_ripulisce_accenti_e_punteggiatura(db):
    dip = _dipendente(db, "D'Amicò M.", "Anna Maria")
    assert _username_libero(db, dip) == "damicom.annamaria"


def test_username_proposto_evita_quelli_gia_in_uso(db, crea_utente):
    crea_utente("rossi.mario", "passwordsegreta", "dipendente")
    dip = _dipendente(db, "Rossi", "Mario")
    assert _username_libero(db, dip) == "rossi.mario2"


def test_elenca_solo_i_dipendenti_senza_accesso(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = Sede(nome="Segreteria Test", colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    con_accesso = _dipendente(db, "Collegato", sede=sede)
    senza_accesso = _dipendente(db, "Scollegato", sede=sede)
    db.add(Utente(username="collegato", password_hash="x", ruolo="dipendente",
                  dipendente_collegato_id=con_accesso.id, attivo=True))
    db.commit()

    r = client.get("/utenti")

    assert r.status_code == 200
    elenco = r.text.split("Dipendenti senza accesso")[1].split("Nuovo utente")[0]
    assert "Scollegato" in elenco
    assert "Collegato Test" not in elenco
    assert str(senza_accesso.id) in elenco


def test_prepara_accesso_precompila_il_modulo(client, crea_utente, db):
    _login_admin(client, crea_utente)
    dip = _dipendente(db, "Pozzi", "Andrea")

    r = client.get(f"/utenti?nuovo_per={dip.id}")

    assert r.status_code == 200
    assert 'value="pozzi.andrea"' in r.text
    assert "Pozzi Andrea" in r.text
    # ruolo "dipendente" preselezionato e persona collegata
    assert '<option value="dipendente" selected>' in r.text
    assert f'<option value="{dip.id}" selected>' in r.text


def test_senza_parametro_il_modulo_resta_vuoto(client, crea_utente, db):
    _login_admin(client, crea_utente)
    _dipendente(db, "Pozzi", "Andrea")

    r = client.get("/utenti")

    assert 'name="username" value=""' in r.text
    assert "selected>" not in r.text.split("Nuovo utente")[1].split("Crea utente")[0]


def test_si_crea_davvero_un_accesso_per_il_dipendente(client, crea_utente, db):
    _login_admin(client, crea_utente)
    dip = _dipendente(db, "Zoppi", "Susanna")

    r = client.post(
        "/utenti/nuovo",
        data={"username": "zoppi.susanna", "password": "passwordsegreta",
              "ruolo": "dipendente", "dipendente_collegato_id": str(dip.id)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    creato = db.query(Utente).filter_by(username="zoppi.susanna").first()
    assert creato is not None
    assert creato.ruolo == "dipendente"
    assert creato.dipendente_collegato_id == dip.id
    # Era l'unico dipendente senza accesso: ora quella sezione sparisce del
    # tutto, invece di restare lì vuota.
    assert "Dipendenti senza accesso" not in client.get("/utenti").text

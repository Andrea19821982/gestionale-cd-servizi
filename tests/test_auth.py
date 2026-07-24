from datetime import date, timedelta

from app import auth
from app.models import Assenza, DelegaApprovazione, Dipendente, Sede
from tests.conftest import login


def test_login_corretto_reindirizza_e_crea_sessione(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    r = login(client, "admin_test", "passwordsegreta")
    assert r.status_code == 303
    r2 = client.get("/dipendenti")
    assert r2.status_code == 200


def test_login_password_sbagliata(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    r = login(client, "admin_test", "sbagliata")
    assert r.status_code == 400
    assert "non corretti" in r.text


def test_route_protetta_senza_login_reindirizza(client):
    r = client.get("/dipendenti", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_consultazione_non_puo_creare_sede(client, crea_utente):
    crea_utente("solo_lettura", "vediemabasta", "consultazione")
    login(client, "solo_lettura", "vediemabasta")
    r = client.post(
        "/sedi/nuova",
        data={"nome": "Sede Fittizia", "colore_hex": "#123456"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_amministratore_puo_creare_sede(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    r = client.post(
        "/sedi/nuova",
        data={"nome": "Sede Fittizia", "colore_hex": "#123456"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r2 = client.get("/sedi")
    assert "Sede Fittizia" in r2.text


def test_autentica_verifica_password_anche_con_username_inesistente(db, monkeypatch):
    """autentica() faceva short-circuit su "utente is None" senza mai
    chiamare verify_password per uno username che non esiste: verify_password
    usa bcrypt, apposta lento (decine/centinaia di ms), quindi un username
    esistente con password sbagliata impiega sempre più tempo a rispondere
    di uno che non esiste affatto. Questa differenza di tempo misurabile è
    un side-channel che permette di scoprire quali username esistono senza
    nemmeno provare a indovinarne la password (enumerazione utenti)."""
    chiamate = []
    originale = auth.verify_password

    def verify_password_spia(password, password_hash):
        chiamate.append(password_hash)
        return originale(password, password_hash)

    monkeypatch.setattr(auth, "verify_password", verify_password_spia)

    risultato = auth.autentica(db, "username_sicuramente_inesistente", "qualunque")
    assert risultato is None
    assert len(chiamate) == 1, "verify_password deve essere chiamata comunque, per non far trapelare col tempo di risposta quali username esistono"


def test_login_rifiuta_next_verso_un_sito_esterno(client, crea_utente):
    """Un "next" che punta fuori dal sito (http://..., //host, /\\host) non
    deve mai essere seguito dopo il login: altrimenti un link malevolo tipo
    /login?next=https://sito-finto.it reindirizzerebbe lì un utente che ha
    appena inserito le sue credenziali vere (open redirect)."""
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    r = client.post(
        "/login",
        data={"username": "admin_test", "password": "passwordsegreta", "next": "https://sito-finto.it/phishing"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_login_rifiuta_next_protocol_relative(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    r = client.post(
        "/login",
        data={"username": "admin_test", "password": "passwordsegreta", "next": "//sito-finto.it/phishing"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_delega_approvazione_non_vale_piu_se_delegato_degradato_a_dipendente(client, crea_utente, db):
    """Una delega di approvazione si può creare solo per un utente con ruolo
    diverso da "dipendente" (vedi /deleghe/nuova in app/routers/utenti.py),
    ma quel controllo vale solo al momento della creazione: se in seguito
    l'amministratore degrada il delegato a "dipendente" (il ruolo di sola
    lettura sui propri dati), la delega esistente non deve più valere.
    Altrimenti un account degradato al ruolo più basso manterrebbe comunque,
    fino alla scadenza della vecchia delega, il potere di approvare o
    rifiutare le richieste di assenza di chiunque."""
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    delegato = crea_utente("delegato_test", "passwordsegreta", "gestore_turni")
    delega = DelegaApprovazione(
        utente_delegato_id=delegato.id,
        data_inizio=date.today() - timedelta(days=1),
        data_fine=date.today() + timedelta(days=1),
    )
    db.add(delega)
    db.commit()

    # L'amministratore degrada il delegato a "dipendente" DOPO la delega.
    r = client.post(
        f"/utenti/{delegato.id}/modifica",
        data={"ruolo": "dipendente", "attivo": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    sede = Sede(nome="Sede Test Delega", colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    dip = Dipendente(cognome="Test", nome="Delega", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    login(client, "delegato_test", "passwordsegreta")
    r2 = client.post(f"/assenze/{assenza.id}/approva", follow_redirects=False)
    assert r2.status_code == 403


def test_navbar_riflette_il_ruolo_aggiornato_senza_rifare_login(client, crea_utente, db):
    """base.html decide cosa mostrare nel menu in base a
    request.session["utente_ruolo"], impostato solo al login (vedi
    esegui_login in app/routers/auth_router.py). I permessi veri sono sempre
    verificati sul ruolo aggiornato nel database (richiedi_ruolo, tramite
    get_utente_corrente), quindi non c'è mai un'escalation reale; ma se un
    altro amministratore cambia il ruolo di un utente con una sessione già
    aperta altrove, quella sessione deve vedere un menu coerente con il
    ruolo attuale alla richiesta successiva, non quello ormai scaduto di
    quando ha fatto login."""
    utente = crea_utente("da_promuovere", "passwordsegreta", "consultazione")
    login(client, "da_promuovere", "passwordsegreta")

    utente.ruolo = "amministratore"
    db.commit()

    r = client.get("/sedi")
    assert r.status_code == 200
    assert 'href="/utenti"' in r.text


def test_login_accetta_next_interno(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    r = client.post(
        "/login",
        data={"username": "admin_test", "password": "passwordsegreta", "next": "/statistiche"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/statistiche"

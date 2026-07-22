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


def test_login_accetta_next_interno(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    r = client.post(
        "/login",
        data={"username": "admin_test", "password": "passwordsegreta", "next": "/statistiche"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/statistiche"

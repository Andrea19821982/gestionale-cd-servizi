"""Il fixture "client" (vedi conftest.py) inietta automaticamente un token
CSRF valido in ogni client.post(), così tutti gli altri test possono
ignorare del tutto questo dettaglio. Questi test verificano invece
esplicitamente che la protezione funzioni, bypassando l'iniezione
automatica con client.request("POST", ...) o passando un token esplicito."""

from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_post_senza_campo_csrf_token_viene_rifiutato(client, crea_utente):
    _login_admin(client, crea_utente)
    # client.request(...) non passa dal wrapper che inietta il token: nessun
    # campo csrf_token nel corpo della richiesta.
    r = client.request(
        "POST", "/sedi/nuova", data={"nome": "Sede Senza Token", "colore_hex": "#123456"},
    )
    assert r.status_code == 422


def test_post_con_csrf_token_sbagliato_viene_rifiutato(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/sedi/nuova",
        data={"nome": "Sede Token Sbagliato", "colore_hex": "#123456", "csrf_token": "questo-non-e-il-token-giusto"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_post_con_csrf_token_corretto_viene_accettato(client, crea_utente):
    _login_admin(client, crea_utente)
    r = client.post(
        "/sedi/nuova",
        data={"nome": "Sede Token Giusto", "colore_hex": "#123456"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_cookie_csrf_impostato_su_pagina_get(client):
    r = client.get("/login")
    assert "csrf_token" in r.cookies

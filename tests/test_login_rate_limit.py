from app.auth import MASSIMO_TENTATIVI_LOGIN
from tests.conftest import login


def test_login_bloccato_dopo_troppi_tentativi_falliti(client, crea_utente):
    crea_utente("utente_bruteforce", "passwordvera", "amministratore")

    for _ in range(MASSIMO_TENTATIVI_LOGIN):
        r = login(client, "utente_bruteforce", "passwordsbagliata")
        assert r.status_code == 400

    # Anche con la password GIUSTA, ora deve essere bloccato.
    r_bloccato = login(client, "utente_bruteforce", "passwordvera")
    assert r_bloccato.status_code == 429
    assert "tentativi" in r_bloccato.text.lower()


def test_login_riuscito_azzera_il_contatore(client, crea_utente):
    crea_utente("utente_normale", "passwordvera", "amministratore")

    for _ in range(MASSIMO_TENTATIVI_LOGIN - 1):
        login(client, "utente_normale", "passwordsbagliata")

    r = login(client, "utente_normale", "passwordvera")
    assert r.status_code == 303  # ancora sotto la soglia: login riuscito

    # Dopo un login riuscito il contatore è azzerato: altri tentativi
    # sbagliati ripartono da zero.
    r2 = login(client, "utente_normale", "passwordsbagliata")
    assert r2.status_code == 400  # non 429: non è bloccato

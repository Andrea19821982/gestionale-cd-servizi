"""Controllo automatico: ogni rotta che modifica dati deve avere sia il
controllo di ruolo sia quello CSRF.

Una revisione del codice ha verificato a mano che tutte le rotte di
scrittura fossero protette, e lo erano. Ma niente garantiva che valesse
anche per la prossima: una rotta nuova aggiunta senza richiedi_ruolo
passava la suite verde, e il buco si sarebbe scoperto solo quando qualcuno
con l'account sbagliato avesse cambiato qualcosa.

Questo test scorre le rotte dell'applicazione vera invece di elencarle a
mano, quindi copre anche quelle che verranno aggiunte in futuro senza che
nessuno debba ricordarsi di aggiornarlo.
"""

from fastapi.routing import APIRoute

from app.main import app

METODI_DI_SCRITTURA = {"POST", "PUT", "PATCH", "DELETE"}

# Le uniche due rotte di scrittura senza controllo di ruolo, per
# costruzione: servono a chi un ruolo non ce l'ha ancora, o non lo ha più.
# Elencate esplicitamente perché un'aggiunta a questa lista si veda in fase
# di revisione, invece di essere nascosta in una condizione generica.
SENZA_RUOLO_PER_PROGETTO = {"/login", "/logout"}


def _rotte_api(rotte):
    """Le rotte annidate dentro i router inclusi non compaiono in
    app.routes come APIRoute: vanno raggiunte scendendo negli oggetti che
    li rappresentano."""
    for rotta in rotte:
        if isinstance(rotta, APIRoute):
            yield rotta
        router_interno = getattr(rotta, "original_router", None)
        if router_interno is not None:
            yield from _rotte_api(router_interno.routes)
        elif getattr(rotta, "routes", None):
            yield from _rotte_api(rotta.routes)


def _rotte_di_scrittura():
    return [r for r in _rotte_api(app.routes) if r.methods & METODI_DI_SCRITTURA]


def _nomi_dipendenze(rotta):
    return {
        getattr(d.call, "__name__", type(d.call).__name__)
        for d in rotta.dependant.dependencies
    }


def test_ogni_rotta_di_scrittura_verifica_il_ruolo():
    mancanti = []
    for rotta in _rotte_di_scrittura():
        if rotta.path in SENZA_RUOLO_PER_PROGETTO:
            continue
        nomi = _nomi_dipendenze(rotta)
        if not any("verifica_ruolo" in n or "approvatore" in n for n in nomi):
            mancanti.append(f"{sorted(rotta.methods)} {rotta.path} -> {sorted(nomi)}")

    assert not mancanti, (
        "Rotte che modificano dati senza controllo di ruolo:\n  " + "\n  ".join(mancanti)
    )


def test_ogni_rotta_di_scrittura_verifica_il_csrf():
    mancanti = []
    for rotta in _rotte_di_scrittura():
        nomi = _nomi_dipendenze(rotta)
        if not any("csrf" in n for n in nomi):
            mancanti.append(f"{sorted(rotta.methods)} {rotta.path} -> {sorted(nomi)}")

    assert not mancanti, (
        "Rotte che modificano dati senza controllo CSRF:\n  " + "\n  ".join(mancanti)
    )


def test_il_controllo_trova_davvero_le_rotte():
    """Se un cambio di FastAPI rompesse la visita ricorsiva, i due test
    sopra passerebbero su una lista vuota senza verificare niente."""
    rotte = _rotte_di_scrittura()
    assert len(rotte) > 30, f"trovate solo {len(rotte)} rotte di scrittura: la visita non funziona"

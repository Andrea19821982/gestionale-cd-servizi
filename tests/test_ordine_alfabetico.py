"""I dipendenti si ordinano sempre per cognome, ovunque.

Prima calendario e anagrafica rispettavano un ordine manuale
(Dipendente.ordine_visualizzazione) che su settanta persone nessuno teneva
aggiornato: inserirne una al posto giusto voleva dire rinumerare mezzo
elenco, e il risultato era un ordine casuale in cui cercare un cognome
significava scorrere tutta la pagina.
"""

from app.models import Dipendente, Sede
from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_ordine", "passwordsegreta", "amministratore")
    login(client, "admin_ordine", "passwordsegreta")


def _sede(db):
    sede = Sede(nome="Sede Ordine", colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _dipendenti_disordinati(db, sede):
    """Cognomi in ordine sparso, con ordine_visualizzazione che li metterebbe
    al contrario: se contasse ancora, l'elenco uscirebbe alla rovescia."""
    for posizione, cognome in enumerate(["Zanetti", "Rossi", "Bianchi"]):
        db.add(Dipendente(
            cognome=cognome, nome="Test", sede_riferimento_id=sede.id,
            attivo=True, ordine_visualizzazione=posizione,
        ))
    db.commit()


def _posizioni(testo, cognomi):
    return [testo.index(c) for c in cognomi]


def test_il_calendario_elenca_in_ordine_alfabetico(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _sede(db)
    _dipendenti_disordinati(db, sede)

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=8")

    assert r.status_code == 200
    posizioni = _posizioni(r.text, ["Bianchi", "Rossi", "Zanetti"])
    assert posizioni == sorted(posizioni)


def test_l_anagrafica_elenca_in_ordine_alfabetico(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _sede(db)
    _dipendenti_disordinati(db, sede)

    r = client.get("/dipendenti")

    assert r.status_code == 200
    posizioni = _posizioni(r.text, ["Bianchi", "Rossi", "Zanetti"])
    assert posizioni == sorted(posizioni)


def test_il_modulo_non_chiede_piu_un_ordine_manuale(client, crea_utente, db):
    """Un campo che non ha più effetto non deve restare nel modulo: sarebbe
    un comando che promette qualcosa e non fa niente."""
    _login_admin(client, crea_utente)
    sede = _sede(db)
    dip = Dipendente(cognome="Solo", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    assert 'name="ordine_visualizzazione"' not in client.get("/dipendenti").text
    assert 'name="ordine_visualizzazione"' not in client.get(f"/dipendenti/{dip.id}/modifica").text


def test_salvare_un_dipendente_non_azzera_il_vecchio_ordine(client, crea_utente, db):
    """Il campo è sparito dal modulo, ma il valore già in archivio non va
    riscritto a zero di soppiatto: semplicemente non si usa più."""
    _login_admin(client, crea_utente)
    sede = _sede(db)
    dip = Dipendente(cognome="Storico", nome="Test", sede_riferimento_id=sede.id,
                     attivo=True, ordine_visualizzazione=7)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        f"/dipendenti/{dip.id}/modifica",
        data={"cognome": "Storico", "nome": "Test", "attivo": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.expire_all()
    assert db.get(Dipendente, dip.id).ordine_visualizzazione == 7

"""La cella ridisegnata dopo una modifica dal calendario.

_cella_calendario.html contiene ormai solo una macro (lo faceva rallentare
di un secondo la stampa di tutte le sedi, quando era un include eseguito
2480 volte). Chi lo renderizzasse come pagina otterrebbe il vuoto: questi
test tengono il ponte al suo posto.
"""

from datetime import date, time

from app.models import AssegnazioneGiornaliera, Assenza, Dipendente, Sede, TipoTurno
from tests.conftest import login


def _preparazione(client, crea_utente, db):
    crea_utente("admin_cella", "passwordsegreta", "amministratore")
    login(client, "admin_cella", "passwordsegreta")
    sede = Sede(nome="Sede Cella", colore_hex="#123456", attivo=True)
    db.add(sede)
    tipo = TipoTurno(etichetta="Mattina Cella", ora_inizio=time(7, 0), ora_fine=time(13, 30), fascia="mattina")
    db.add(tipo)
    db.commit()
    db.refresh(sede)
    db.refresh(tipo)
    dip = Dipendente(cognome="Cella", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return sede, tipo, dip


def test_la_cella_aggiornata_non_torna_vuota(client, crea_utente, db):
    _, tipo, dip = _preparazione(client, crea_utente, db)

    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-12", "tipo_turno_id": str(tipo.id)},
    )

    assert r.status_code == 200
    assert "<td" in r.text, "la cella è tornata vuota: il ponte alla macro non funziona"
    assert f'id="cella-{dip.id}-2026-08-12"' in r.text
    assert "select-cella-overlay" in r.text  # l'amministratore può ancora cambiare il turno


def test_la_cella_aggiornata_mantiene_il_tag_dell_assenza_a_orario(client, crea_utente, db):
    """Cambiando il turno, il tag dell'assenza a orario spariva dalla cella
    finché non si ricaricava la pagina: la cella tornava indietro rispetto a
    com'era un attimo prima."""
    _, tipo, dip = _preparazione(client, crea_utente, db)
    db.add(Assenza(
        dipendente_id=dip.id, data_inizio=date(2026, 8, 12), data_fine=date(2026, 8, 12),
        tipo_assenza="Permesso", stato="approvata", ora_inizio=time(12, 0), ora_fine=time(19, 0),
    ))
    db.commit()

    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-12", "tipo_turno_id": str(tipo.id)},
    )

    assert r.status_code == 200
    assert "A 12:00-19:00" in r.text


def test_la_cella_svuotata_resta_una_cella(client, crea_utente, db):
    _, tipo, dip = _preparazione(client, crea_utente, db)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 8, 12), sede_effettiva_id=dip.sede_riferimento_id,
        tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    r = client.post(
        "/calendario/cella",
        data={"dipendente_id": dip.id, "data": "2026-08-12", "tipo_turno_id": ""},
    )

    assert r.status_code == 200
    assert f'id="cella-{dip.id}-2026-08-12"' in r.text

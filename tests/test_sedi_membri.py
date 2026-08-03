"""Assegnazione dei dipendenti a una sede direttamente dal suo modulo.

Prima si poteva fare solo aprendo una per una le schede in Dipendenti dopo
aver creato la sede, mentre per i comparti la scelta era già lì.
"""

from app.models import Dipendente, Sede, SottosezioneCopertura
from tests.conftest import login


def _login_admin(client, crea_utente):
    crea_utente("admin_sedi_membri", "passwordsegreta", "amministratore")
    login(client, "admin_sedi_membri", "passwordsegreta")


def _sede(db, nome):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _dipendente(db, cognome, sede=None, sottosezione=None, attivo=True):
    dip = Dipendente(
        cognome=cognome, nome="Test", attivo=attivo,
        sede_riferimento_id=sede.id if sede else None,
        sottosezione=sottosezione,
    )
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def _crea_sede(client, nome, dipendente_ids=()):
    return client.post(
        "/sedi/nuova",
        data={
            "nome": nome, "colore_hex": "#2563eb",
            "copertura_minima_mattina": "0", "copertura_minima_pomeriggio": "0",
            "ordine_visualizzazione": "0",
            "dipendente_ids": [str(i) for i in dipendente_ids],
        },
        follow_redirects=False,
    )


def test_creando_una_sede_si_assegnano_subito_i_dipendenti(client, crea_utente, db):
    _login_admin(client, crea_utente)
    vecchia = _sede(db, "Vecchia")
    primo = _dipendente(db, "Primo", vecchia)
    secondo = _dipendente(db, "Secondo", vecchia)
    fermo = _dipendente(db, "Fermo", vecchia)

    r = _crea_sede(client, "Segreteria Test", [primo.id, secondo.id])
    assert r.status_code == 303

    db.expire_all()
    nuova = db.query(Sede).filter_by(nome="Segreteria Test").first()
    assert nuova is not None
    assert db.get(Dipendente, primo.id).sede_riferimento_id == nuova.id
    assert db.get(Dipendente, secondo.id).sede_riferimento_id == nuova.id
    assert db.get(Dipendente, fermo.id).sede_riferimento_id == vecchia.id


def test_chi_viene_spostato_perde_il_comparto_della_sede_di_prima(client, crea_utente, db):
    """I comparti appartengono a una sede precisa: portarsi dietro il nome
    di un comparto di un altro palazzo creerebbe un gruppo che non
    corrisponde a niente, col minimo di copertura ricaduto a 0 in silenzio."""
    _login_admin(client, crea_utente)
    valdina = _sede(db, "Valdina Test")
    db.add(SottosezioneCopertura(sede_id=valdina.id, nome="Parcheggio", copertura_minima_mattina=1, copertura_minima_pomeriggio=1))
    db.commit()
    parcheggiatore = _dipendente(db, "Parcheggiatore", valdina, sottosezione="Parcheggio")

    _crea_sede(client, "Sede Nuova Test", [parcheggiatore.id])

    db.expire_all()
    spostato = db.get(Dipendente, parcheggiatore.id)
    assert spostato.sede_riferimento_id != valdina.id
    assert spostato.sottosezione is None


def test_una_sede_creata_senza_spunte_resta_vuota(client, crea_utente, db):
    _login_admin(client, crea_utente)
    altra = _sede(db, "Altra")
    dip = _dipendente(db, "Immobile", altra)

    _crea_sede(client, "Sede Vuota Test")

    db.expire_all()
    assert db.get(Dipendente, dip.id).sede_riferimento_id == altra.id


def test_modificando_una_sede_si_aggiungono_e_tolgono_persone(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _sede(db, "Sede Da Modificare")
    altrove = _sede(db, "Altrove")
    dentro = _dipendente(db, "Dentro", sede)
    fuori = _dipendente(db, "Fuori", altrove)

    r = client.post(
        f"/sedi/{sede.id}/modifica",
        data={
            "nome": sede.nome, "colore_hex": sede.colore_hex,
            "copertura_minima_mattina": "0", "copertura_minima_pomeriggio": "0",
            "ordine_visualizzazione": "0", "attivo": "on",
            "dipendente_ids": [str(fuori.id)],  # entra "Fuori", esce "Dentro"
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db.expire_all()
    assert db.get(Dipendente, fuori.id).sede_riferimento_id == sede.id
    # Chi viene tolto resta senza sede: va riassegnato, non sparisce.
    assert db.get(Dipendente, dentro.id).sede_riferimento_id is None


def test_i_disattivati_non_vengono_toccati(client, crea_utente, db):
    """L'elenco mostra solo gli attivi: un disattivato non spuntato non
    deve per questo perdere la sede a cui era assegnato."""
    _login_admin(client, crea_utente)
    sede = _sede(db, "Sede Con Disattivato")
    disattivato = _dipendente(db, "Disattivato", sede, attivo=False)

    client.post(
        f"/sedi/{sede.id}/modifica",
        data={
            "nome": sede.nome, "colore_hex": sede.colore_hex,
            "copertura_minima_mattina": "0", "copertura_minima_pomeriggio": "0",
            "ordine_visualizzazione": "0", "attivo": "on",
        },
        follow_redirects=False,
    )

    db.expire_all()
    assert db.get(Dipendente, disattivato.id).sede_riferimento_id == sede.id


def test_la_pagina_sedi_mostra_l_elenco_da_spuntare(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _sede(db, "Sede Elenco")
    _dipendente(db, "Spuntabile", sede)

    r = client.get("/sedi")

    assert r.status_code == 200
    assert "Chi lavora in questa sede" in r.text
    assert "Spuntabile" in r.text

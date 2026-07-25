import pytest
from sqlalchemy.exc import IntegrityError

from app.auth import hash_password
from app.models import Sede, TipoTurno, Utente
from tests.conftest import login


def test_username_univoco(db):
    db.add(Utente(username="doppio", password_hash=hash_password("x"), ruolo="consultazione"))
    db.commit()
    db.add(Utente(username="doppio", password_hash=hash_password("y"), ruolo="consultazione"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_gestore_turni_non_puo_creare_sede(client, crea_utente):
    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")
    r = client.post(
        "/sedi/nuova",
        data={"nome": "Sede Fittizia", "colore_hex": "#123456"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_gestore_turni_puo_creare_dipendente(client, crea_utente):
    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")
    r = client.post(
        "/dipendenti/nuovo",
        data={"cognome": "Fittizio", "nome": "Test", "sede_riferimento_id": "", "ordine_visualizzazione": 0},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r2 = client.get("/dipendenti")
    assert "Fittizio" in r2.text


def test_crea_e_modifica_tipo_turno(client, crea_utente, db):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    r = client.post(
        "/tipi-turno/nuovo",
        data={"etichetta": "Notte Test", "ora_inizio": "22:00", "ora_fine": "06:00"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    tipo = db.query(TipoTurno).filter_by(etichetta="Notte Test").first()
    assert tipo is not None

    r2 = client.post(
        f"/tipi-turno/{tipo.id}/modifica",
        data={"etichetta": "Notte Test Modificata", "ora_inizio": "23:00", "ora_fine": "05:00"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    db.expire_all()
    tipo_aggiornato = db.query(TipoTurno).filter_by(id=tipo.id).first()
    assert tipo_aggiornato.etichetta == "Notte Test Modificata"


def test_costo_orario_non_numerico_da_400_non_500(client, crea_utente):
    """Prima del fix, un valore non numerico in costo_orario faceva
    esplodere float(valore) con un 500 non gestito invece di un 400 chiaro."""
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    r = client.post(
        "/dipendenti/nuovo",
        data={"cognome": "Test", "nome": "CostoErrato", "costo_orario": "non-un-numero"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_costo_orario_negativo_rifiutato(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    r = client.post(
        "/dipendenti/nuovo",
        data={"cognome": "Test", "nome": "CostoNegativo", "costo_orario": "-5"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_costo_orario_zero_viene_salvato_come_zero_non_come_vuoto(client, crea_utente, db):
    from app.models import Dipendente

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    r = client.post(
        "/dipendenti/nuovo",
        data={"cognome": "Test", "nome": "CostoZero", "costo_orario": "0"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    dip = db.query(Dipendente).filter_by(cognome="Test", nome="CostoZero").first()
    assert dip.costo_orario == 0.0


def test_ore_settimanali_fuori_range_rifiutate(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    r = client.post(
        "/dipendenti/nuovo",
        data={"cognome": "Test", "nome": "OreAssurde", "ore_settimanali_contrattuali": "200"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    r2 = client.post(
        "/dipendenti/nuovo",
        data={"cognome": "Test", "nome": "OreNegative", "ore_settimanali_contrattuali": "0"},
        follow_redirects=False,
    )
    assert r2.status_code == 400


def test_storico_dipendente_mostra_costo_orario_zero_non_trattino(client, crea_utente, db):
    from app.models import Dipendente, Sede

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    sede = Sede(nome="Sede Storico", colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    dip = Dipendente(cognome="Storico", nome="CostoZero", sede_riferimento_id=sede.id, attivo=True, costo_orario=0.0)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get(f"/dipendenti/{dip.id}/storico")
    assert r.status_code == 200
    riga = r.text.split("Costo orario")[1].split("</tr>")[0]
    assert "0.00" in riga
    assert "—" not in riga


def test_form_modifica_precompila_costo_orario_zero(client, crea_utente, db):
    """La pagina /dipendenti/{id}/modifica deve precompilare il campo
    costo_orario con "0" quando il valore salvato è 0.0, non lasciarlo
    vuoto: altrimenti chi apre il form per cambiare un altro campo (es. il
    nome) e salva senza toccare costo_orario finirebbe per azzerarlo
    silenziosamente a "nessun costo impostato" (None) invece di 0."""
    from app.models import Dipendente

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    dip = Dipendente(cognome="Test", nome="CostoZeroForm", attivo=True, costo_orario=0.0)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get(f"/dipendenti/{dip.id}/modifica")
    assert r.status_code == 200
    campo_costo = r.text.split('name="costo_orario"')[1].split(">")[0]
    assert 'value="0.0"' in campo_costo or 'value="0"' in campo_costo


def test_pagina_dipendenti_non_ha_piu_form_inline_ma_link_a_pagina_dedicata(client, crea_utente, db):
    """La modifica non è più un pannello a comparsa dentro la riga della
    tabella (mai abbastanza spazio per il form con tutti i campi): ora è un
    link a una pagina intera dedicata."""
    from app.models import Dipendente

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    dip = Dipendente(cognome="Link", nome="Modifica", attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get("/dipendenti")
    assert r.status_code == 200
    assert f'href="/dipendenti/{dip.id}/modifica"' in r.text
    assert "<details>" not in r.text


def test_pagina_modifica_dipendente_mostra_tutti_i_campi(client, crea_utente, db):
    from app.models import Dipendente

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    dip = Dipendente(cognome="Pagina", nome="Intera", attivo=True, sottosezione="Parcheggio")
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get(f"/dipendenti/{dip.id}/modifica")
    assert r.status_code == 200
    assert 'value="Pagina"' in r.text
    assert 'value="Intera"' in r.text
    assert 'value="Parcheggio"' in r.text
    assert "Pattern turno" in r.text


def test_pagina_modifica_dipendente_richiede_ruolo_operativo(client, crea_utente, db):
    from app.models import Dipendente

    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    dip = Dipendente(cognome="Negato", nome="Test", attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.get(f"/dipendenti/{dip.id}/modifica")
    assert r.status_code == 403


def test_pagina_modifica_dipendente_inesistente_da_404(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    r = client.get("/dipendenti/9999/modifica")
    assert r.status_code == 404


def test_salvare_anagrafica_torna_alla_pagina_di_modifica(client, crea_utente, db):
    from app.models import Dipendente

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    dip = Dipendente(cognome="Redirect", nome="Test", attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        f"/dipendenti/{dip.id}/modifica",
        data={"cognome": "Redirect", "nome": "Test", "sede_riferimento_id": "", "ordine_visualizzazione": 0},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/dipendenti/{dip.id}/modifica"


def test_disattivare_dipendente_con_account_collegato_mostra_avviso(client, crea_utente, db):
    from app.models import Dipendente

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    dip = Dipendente(cognome="Collegato", nome="Test", attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    crea_utente("dipendente_collegato", "passwordsegreta", "dipendente")
    utente_collegato = db.query(Utente).filter_by(username="dipendente_collegato").first()
    utente_collegato.dipendente_collegato_id = dip.id
    db.commit()

    r = client.post(
        f"/dipendenti/{dip.id}/modifica",
        data={"cognome": dip.cognome, "nome": dip.nome},  # niente "attivo" -> disattivato
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "dipendente_collegato" in r.text
    assert "disattivato" in r.text.lower()


def test_disattivare_dipendente_senza_account_non_mostra_avviso(client, crea_utente, db):
    from app.models import Dipendente

    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    dip = Dipendente(cognome="SenzaAccount", nome="Test", attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        f"/dipendenti/{dip.id}/modifica",
        data={"cognome": dip.cognome, "nome": dip.nome},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "flash-avviso" not in r.text


def test_modifica_sede_disattiva(client, crea_utente, db):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    db.add(Sede(nome="Sede Da Disattivare", colore_hex="#000000", attivo=True))
    db.commit()
    sede = db.query(Sede).filter_by(nome="Sede Da Disattivare").first()

    r = client.post(
        f"/sedi/{sede.id}/modifica",
        data={"nome": sede.nome, "colore_hex": sede.colore_hex},  # niente "attivo" -> deve diventare False
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.expire_all()
    sede_aggiornata = db.query(Sede).filter_by(id=sede.id).first()
    assert sede_aggiornata.attivo is False

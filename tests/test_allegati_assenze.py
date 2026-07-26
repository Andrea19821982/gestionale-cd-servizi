from app.models import Assenza, Dipendente, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_allegato_valido_viene_salvato_e_scaricabile(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="Allegato", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        files={"allegato": ("certificato.pdf", b"%PDF-1.4 contenuto finto", "application/pdf")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    assert assenza.allegato_nome == "certificato.pdf"
    assert assenza.allegato_path is not None

    r2 = client.get(f"/assenze/{assenza.id}/allegato")
    assert r2.status_code == 200
    assert r2.content == b"%PDF-1.4 contenuto finto"


def test_allegato_con_estensione_non_ammessa_viene_rifiutato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="EstensioneErrata", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        files={"allegato": ("virus.exe", b"contenuto", "application/octet-stream")},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert db.query(Assenza).filter_by(dipendente_id=dip.id).first() is None


def test_allegato_troppo_grande_viene_rifiutato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="FileGrande", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    contenuto_grande = b"0" * (5 * 1024 * 1024 + 1)
    r = client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        files={"allegato": ("certificato.pdf", contenuto_grande, "application/pdf")},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_assenza_senza_allegato_non_ha_link_di_download(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    dip = Dipendente(cognome="Test", nome="SenzaAllegato", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)

    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Ferie"},
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()

    r = client.get(f"/assenze/{assenza.id}/allegato")
    assert r.status_code == 404


def _assenza_con_allegato(client, db, cognome):
    """Crea un'assenza con certificato allegato, come amministratore, e
    restituisce l'id dell'assenza."""
    sede = _crea_sede(db, f"Sede {cognome}")
    dip = Dipendente(cognome=cognome, nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    client.post(
        "/assenze/nuova",
        data={"dipendente_id": dip.id, "data_inizio": "2026-08-10", "data_fine": "2026-08-11", "tipo_assenza": "Malattia"},
        files={"allegato": ("certificato.pdf", b"%PDF-1.4 dati sanitari", "application/pdf")},
        follow_redirects=False,
    )
    assenza = db.query(Assenza).filter_by(dipendente_id=dip.id).first()
    return dip, assenza


def test_consultazione_non_puo_scaricare_i_certificati_medici(client, crea_utente, db):
    """Il certificato allegato a un'assenza è un dato sanitario. Il ruolo
    "consultazione" si dà a chi deve solo guardare il calendario: prima
    bastava che cambiasse il numero nell'indirizzo per scaricarsi
    l'archivio dei certificati di tutti."""
    _login_admin(client, crea_utente)
    _, assenza = _assenza_con_allegato(client, db, "Riservato")
    assert assenza.allegato_path  # l'allegato c'è davvero, il test ha senso

    crea_utente("sola_lettura", "passwordsegreta", "consultazione")
    login(client, "sola_lettura", "passwordsegreta")

    r = client.get(f"/assenze/{assenza.id}/allegato", follow_redirects=False)

    assert r.status_code == 403


def test_dipendente_non_puo_scaricare_i_certificati_medici(client, crea_utente, db):
    _login_admin(client, crea_utente)
    _, assenza = _assenza_con_allegato(client, db, "Riservatissimo")

    crea_utente("dip_test", "passwordsegreta", "dipendente")
    login(client, "dip_test", "passwordsegreta")

    r = client.get(f"/assenze/{assenza.id}/allegato", follow_redirects=False)

    assert r.status_code == 403


def test_chi_gestisce_le_assenze_scarica_ancora_il_certificato(client, crea_utente, db):
    """Il contraltare dei due test sopra: la restrizione non deve aver
    tolto l'allegato anche a chi le assenze le gestisce per lavoro."""
    _login_admin(client, crea_utente)
    _, assenza = _assenza_con_allegato(client, db, "Gestibile")

    crea_utente("gestore_test", "passwordsegreta", "gestore_turni")
    login(client, "gestore_test", "passwordsegreta")

    r = client.get(f"/assenze/{assenza.id}/allegato")

    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 dati sanitari"
    # PC condivisi: il certificato non deve restare nella cache del browser.
    assert r.headers.get("cache-control") == "no-store"


def test_consultazione_non_vede_il_link_al_certificato_ne_il_costo_orario(client, crea_utente, db):
    """Nascondere il link non protegge il dato (lo fa il controllo di ruolo
    sulla rotta), ma evita di mostrare a chi non può scaricarlo un comando
    che darebbe errore, e di rivelare quali assenze hanno un certificato."""
    _login_admin(client, crea_utente)
    dip, assenza = _assenza_con_allegato(client, db, "Nascosto")
    dip.costo_orario = 17.50
    db.commit()

    crea_utente("sola_lettura2", "passwordsegreta", "consultazione")
    login(client, "sola_lettura2", "passwordsegreta")

    pagina_assenze = client.get("/assenze").text
    assert f"/assenze/{assenza.id}/allegato" not in pagina_assenze

    storico = client.get(f"/dipendenti/{dip.id}/storico").text
    assert f"/assenze/{assenza.id}/allegato" not in storico
    assert "Costo orario" not in storico
    assert "17.50" not in storico

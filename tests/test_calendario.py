from calendar import monthrange
from datetime import date

from app.models import Dipendente, Sede
from tests.conftest import login


def _crea_sede(db, nome="Sede Test", colore="#123456"):
    sede = Sede(nome=nome, colore_hex=colore, attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def test_numero_colonne_giorno_corretto_per_mese(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    db.add(Dipendente(cognome="Test", nome="Uno", sede_riferimento_id=sede.id, attivo=True))
    db.commit()

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=2")
    assert r.status_code == 200
    giorni_febbraio_2026 = monthrange(2026, 2)[1]
    assert giorni_febbraio_2026 == 28
    # un'intestazione con l'iniziale del giorno per ciascun giorno del mese
    assert r.text.count('<span class="muted">') == 28


def test_weekend_evidenziati_correttamente(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    db.add(Dipendente(cognome="Test", nome="Uno", sede_riferimento_id=sede.id, attivo=True))
    db.commit()

    anno, mese = 2026, 7
    numero_giorni = monthrange(anno, mese)[1]
    weekend_attesi = sum(
        1 for g in range(1, numero_giorni + 1) if date(anno, mese, g).weekday() >= 5
    )

    r = client.get(f"/calendario?sede_id={sede.id}&anno={anno}&mese={mese}")
    assert r.status_code == 200
    # ogni giorno di weekend produce sia un <th class="weekend"> che un <td class="weekend">
    assert r.text.count('class="weekend"') == weekend_attesi * 2


def test_dipendenti_filtrati_per_sede(client, crea_utente, db):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")

    sede_a = _crea_sede(db, "Sede A", "#111111")
    sede_b = _crea_sede(db, "Sede B", "#222222")
    db.add(Dipendente(cognome="DellaSedeA", nome="Test", sede_riferimento_id=sede_a.id, attivo=True))
    db.add(Dipendente(cognome="DellaSedeB", nome="Test", sede_riferimento_id=sede_b.id, attivo=True))
    db.commit()

    r = client.get(f"/calendario?sede_id={sede_a.id}&anno=2026&mese=7")
    assert "DellaSedeA" in r.text
    assert "DellaSedeB" not in r.text


def test_consultazione_puo_vedere_calendario(client, crea_utente, db):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    sede = _crea_sede(db)
    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=7")
    assert r.status_code == 200


def test_calendario_richiede_login(client):
    r = client.get("/calendario", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_assenza_mostra_assente_per_esteso_non_abbreviato(client, crea_utente, db):
    """Sia nella vista modificabile (amministratore/gestore turni) sia in
    quella di sola lettura, un'assenza deve mostrare la parola per intero
    "ASSENTE", non l'abbreviazione "ASS" usata in precedenza nella vista
    modificabile."""
    from app.models import AssegnazioneGiornaliera

    crea_utente("admin_ass_test", "passwordsegreta", "amministratore")
    login(client, "admin_ass_test", "passwordsegreta")
    sede = _crea_sede(db, "Sede Assenza Test")
    dip = Dipendente(cognome="Assente", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=date(2026, 7, 10), sede_effettiva_id=sede.id,
        tipo_turno_id=None, origine="assenza",
    ))
    db.commit()

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=7")
    assert r.status_code == 200
    assert ">ASSENTE<" in r.text
    assert ">ASS<" not in r.text


def test_raggruppa_per_sottosezione_ordina_senza_gruppo_prima_poi_i_gruppi():
    from app.routers.calendario import _raggruppa_per_sottosezione

    class Finto:
        def __init__(self, id, sottosezione=None):
            self.id = id
            self.sottosezione = sottosezione

    a = Finto(1)
    b = Finto(2, "Parcheggio")
    c = Finto(3)
    d = Finto(4, "Parcheggio")
    e = Finto(5, "Archivio")

    riordinati, titoli = _raggruppa_per_sottosezione([a, b, c, d, e])

    assert [x.id for x in riordinati] == [1, 3, 2, 4, 5]
    assert titoli == {2: "Parcheggio", 5: "Archivio"}


def test_calendario_mostra_sezione_sottosezione_con_i_membri_raggruppati(client, crea_utente, db):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")
    sede = _crea_sede(db)
    db.add(Dipendente(cognome="Normale", nome="Uno", sede_riferimento_id=sede.id, attivo=True))
    db.add(Dipendente(cognome="Parcheggiato", nome="Due", sede_riferimento_id=sede.id, attivo=True, sottosezione="Parcheggio"))
    db.add(Dipendente(cognome="Normale", nome="Tre", sede_riferimento_id=sede.id, attivo=True))
    db.commit()

    r = client.get(f"/calendario?sede_id={sede.id}&anno=2026&mese=7")
    assert r.status_code == 200
    assert "Parcheggio" in r.text
    # Il dipendente della sottosezione compare dopo entrambi quelli senza gruppo.
    pos_normale_uno = r.text.index("Normale Uno")
    pos_normale_tre = r.text.index("Normale Tre")
    pos_sezione = r.text.index("Parcheggio")
    pos_parcheggiato = r.text.index("Parcheggiato Due")
    assert pos_normale_uno < pos_sezione
    assert pos_normale_tre < pos_sezione
    assert pos_sezione < pos_parcheggiato

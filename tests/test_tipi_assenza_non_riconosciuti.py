"""Diciture di assenza che sfuggono al conteggio delle ferie residue.

Assenza.tipo_assenza è testo libero e il conteggio delle ferie cerca la
parola "ferie" nel testo: chi scrive "Congedo annuale" crea un'assenza che
non viene scalata dal monte ferie, senza nessun errore da nessuna parte.
Non si può indovinare l'intenzione, ma si deve far notare il caso.
"""

from datetime import date

from app.models import Assenza, Dipendente, Sede
from app.routers.statistiche import tipi_assenza_non_riconosciuti
from tests.conftest import login


def _dipendente(db, cognome="Prova"):
    sede = Sede(nome=f"Sede {cognome}", colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    dip = Dipendente(cognome=cognome, nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def _assenza(db, dip, tipo, stato="approvata", anno=2026):
    db.add(Assenza(
        dipendente_id=dip.id,
        data_inizio=date(anno, 3, 1),
        data_fine=date(anno, 3, 3),
        tipo_assenza=tipo,
        stato=stato,
    ))
    db.commit()


def test_le_diciture_note_non_vengono_segnalate(db):
    dip = _dipendente(db)
    for tipo in ("Ferie", "ferie estive", "MALATTIA", "Permesso retribuito"):
        _assenza(db, dip, tipo)

    assert tipi_assenza_non_riconosciuti(db, 2026) == []


def test_una_dicitura_estranea_viene_segnalata_col_conteggio(db):
    dip = _dipendente(db)
    _assenza(db, dip, "Congedo annuale")
    _assenza(db, dip, "Congedo annuale")
    _assenza(db, dip, "Aspettativa")
    _assenza(db, dip, "Ferie")

    assert tipi_assenza_non_riconosciuti(db, 2026) == [("Congedo annuale", 2), ("Aspettativa", 1)]


def test_solo_le_assenze_approvate_contano(db):
    """Una richiesta ancora da decidere, o rifiutata, non incide sulle ferie
    residue: segnalarla sarebbe un falso allarme."""
    dip = _dipendente(db)
    _assenza(db, dip, "Congedo annuale", stato="richiesta")
    _assenza(db, dip, "Aspettativa", stato="rifiutata")

    assert tipi_assenza_non_riconosciuti(db, 2026) == []


def test_le_assenze_di_un_altro_anno_non_contano(db):
    dip = _dipendente(db)
    _assenza(db, dip, "Congedo annuale", anno=2025)

    assert tipi_assenza_non_riconosciuti(db, 2026) == []
    assert tipi_assenza_non_riconosciuti(db, 2025) == [("Congedo annuale", 1)]


def test_la_pagina_statistiche_mostra_l_avviso(client, crea_utente, db):
    crea_utente("admin_tipi", "passwordsegreta", "amministratore")
    login(client, "admin_tipi", "passwordsegreta")
    dip = _dipendente(db, "Segnalato")
    _assenza(db, dip, "Congedo annuale")

    r = client.get("/statistiche?anno=2026")

    assert r.status_code == 200
    assert "non rientrano in nessuna categoria nota" in r.text
    assert "Congedo annuale" in r.text


def test_senza_diciture_estranee_nessun_avviso(client, crea_utente, db):
    crea_utente("admin_tipi2", "passwordsegreta", "amministratore")
    login(client, "admin_tipi2", "passwordsegreta")
    dip = _dipendente(db, "Pulito")
    _assenza(db, dip, "Ferie")

    r = client.get("/statistiche?anno=2026")

    assert r.status_code == 200
    assert "non rientrano in nessuna categoria nota" not in r.text

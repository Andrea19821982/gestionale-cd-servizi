"""Verifica che l'esempio già compilato mostrato nei moduli PDF (assenze e
sostituzioni, vedi app/routers/bozze_email.py) sia davvero nel formato che
app/email_ingest.py sa interpretare da solo: un modulo che sembra corretto
ma che il programma non capisce sarebbe peggio di nessun modulo, perché
darebbe ai dipendenti un falso senso di sicurezza."""

from datetime import date

from app.email_ingest import analizza_email
from app.models import Dipendente, Sede
from app.routers.bozze_email import (
    esempio_corpo_assenza,
    esempio_corpo_sostituzione,
    genera_modulo_assenza,
    genera_modulo_sostituzione,
)


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _crea_dipendente(db, cognome, nome, sede):
    dip = Dipendente(cognome=cognome, nome=nome, sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    return dip


def test_esempio_modulo_assenza_interpretato_senza_errori(db):
    sede = _crea_sede(db)
    dip = _crea_dipendente(db, "Rossi", "Mario", sede)

    risultato = analizza_email(db, "ASSENZA", esempio_corpo_assenza())

    assert risultato["tipo"] == "assenza"
    assert risultato["errore_parsing"] is None
    assert risultato["dipendente_id"] == dip.id
    assert risultato["tipo_assenza"] == "Ferie"
    assert risultato["data_inizio"] == date(2026, 8, 10)
    assert risultato["data_fine"] == date(2026, 8, 14)
    assert risultato["note"] == "rientro il 15"


def test_esempio_modulo_sostituzione_interpretato_senza_errori(db):
    sede = _crea_sede(db)
    assente = _crea_dipendente(db, "Rossi", "Mario", sede)
    sostituto = _crea_dipendente(db, "Verdi", "Luca", sede)

    risultato = analizza_email(db, "SOSTITUZIONE", esempio_corpo_sostituzione())

    assert risultato["tipo"] == "sostituzione"
    assert risultato["errore_parsing"] is None
    assert risultato["dipendente_id"] == assente.id
    assert risultato["dipendente_sostituto_id"] == sostituto.id
    assert risultato["data_inizio"] == date(2026, 8, 10)
    assert risultato["ora_inizio"] is None  # "intera giornata" = nessun orario
    assert risultato["ora_fine"] is None


def test_modulo_assenza_contiene_esempio_ed_e_incluso_nel_testo_generato():
    testo = genera_modulo_assenza("turni@cdservizi.it")
    assert "turni@cdservizi.it" in testo
    assert "Oggetto dell'email (scrivilo esattamente così nel campo oggetto): ASSENZA" in testo
    assert esempio_corpo_assenza() in testo
    # Non deve contenere il modulo/istruzioni delle sostituzioni.
    assert "SOSTITUZIONE" not in testo


def test_modulo_sostituzione_contiene_esempio_ed_e_incluso_nel_testo_generato():
    testo = genera_modulo_sostituzione("turni@cdservizi.it")
    assert "turni@cdservizi.it" in testo
    assert "Oggetto dell'email (scrivilo esattamente così nel campo oggetto): SOSTITUZIONE" in testo
    assert esempio_corpo_sostituzione() in testo
    assert "ASSENZA" not in testo

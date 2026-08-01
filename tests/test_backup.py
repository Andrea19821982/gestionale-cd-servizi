import os
import sqlite3
from datetime import datetime, timedelta

import pytest

from app import backup, config


@pytest.fixture(autouse=True)
def _azzera_memoria_fallimenti(monkeypatch):
    """_giorno_ultimo_tentativo_fallito è stato di modulo: senza azzerarlo,
    un test che fa fallire il backup zittirebbe quelli successivi."""
    monkeypatch.setattr(backup, "_giorno_ultimo_tentativo_fallito", None)


def _db_di_prova(tmp_path):
    percorso = tmp_path / "turni.db"
    conn = sqlite3.connect(str(percorso))
    conn.execute("CREATE TABLE prova (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return percorso


def _db_danneggiato(tmp_path):
    """Un file che si apre come database ma è rovinato: l'header è quello
    giusto, il resto no. È il modo più fedele di riprodurre il caso vero
    senza dipendere da come SQLite dispone le pagine."""
    percorso = _db_di_prova(tmp_path)
    for _ in range(200):
        conn = sqlite3.connect(str(percorso))
        conn.execute("INSERT INTO prova DEFAULT VALUES")
        conn.commit()
        conn.close()
    contenuto = bytearray(percorso.read_bytes())
    for posizione in range(4096, len(contenuto)):
        contenuto[posizione] = 0x5A
    percorso.write_bytes(bytes(contenuto))
    return percorso


def test_esegui_backup_crea_una_copia_funzionante(tmp_path, monkeypatch):
    db_path = _db_di_prova(tmp_path)
    cartella_backup = tmp_path / "backup"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella_backup)

    destinazione = backup.esegui_backup()

    assert destinazione is not None
    assert destinazione.exists()
    conn = sqlite3.connect(str(destinazione))
    tabelle = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    assert ("prova",) in tabelle


def test_esegui_backup_senza_database_non_fa_nulla(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "non_esiste.db")
    monkeypatch.setattr(config, "BACKUP_CARTELLA", tmp_path / "backup")

    assert backup.esegui_backup() is None


def test_pulisci_backup_vecchi_rimuove_solo_i_superati(tmp_path, monkeypatch):
    cartella_backup = tmp_path / "backup"
    cartella_backup.mkdir()
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella_backup)
    monkeypatch.setattr(config, "BACKUP_RETENZIONE_GIORNI", 30)
    monkeypatch.setattr(config, "BACKUP_MINIMI_DA_CONSERVARE", 1)

    vecchio = cartella_backup / "turni_2000-01-01_000000.db"
    vecchio.write_text("x")
    recente = cartella_backup / "turni_recente_000000.db"
    recente.write_text("x")

    vecchio_timestamp = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(vecchio, (vecchio_timestamp, vecchio_timestamp))

    backup._pulisci_backup_vecchi()

    assert not vecchio.exists()
    assert recente.exists()


def test_controlla_e_backup_se_dovuto_disabilitato_non_fa_nulla(tmp_path, monkeypatch):
    db_path = _db_di_prova(tmp_path)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BACKUP_CARTELLA", tmp_path / "backup")
    monkeypatch.setattr(config, "BACKUP_ABILITATO", False)

    assert backup.controlla_e_backup_se_dovuto() is False
    assert not (tmp_path / "backup").exists()


def test_controlla_e_backup_se_dovuto_rispetta_orario_configurato(tmp_path, monkeypatch):
    db_path = _db_di_prova(tmp_path)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BACKUP_CARTELLA", tmp_path / "backup")
    monkeypatch.setattr(config, "BACKUP_ABILITATO", True)
    monkeypatch.setattr(config, "BACKUP_ORA", "23:59")

    assert backup.controlla_e_backup_se_dovuto() is False
    assert not (tmp_path / "backup").exists()


def test_controlla_e_backup_se_dovuto_non_ripete_lo_stesso_giorno(tmp_path, monkeypatch):
    db_path = _db_di_prova(tmp_path)
    cartella_backup = tmp_path / "backup"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella_backup)
    monkeypatch.setattr(config, "BACKUP_ABILITATO", True)
    monkeypatch.setattr(config, "BACKUP_ORA", "00:00")

    assert backup.controlla_e_backup_se_dovuto() is True
    numero_file_dopo_primo_backup = len(list(cartella_backup.iterdir()))
    assert numero_file_dopo_primo_backup == 1

    assert backup.controlla_e_backup_se_dovuto() is False
    assert len(list(cartella_backup.iterdir())) == numero_file_dopo_primo_backup


def test_un_backup_non_integro_viene_scartato_e_non_tocca_i_precedenti(tmp_path, monkeypatch):
    """Il caso che conta davvero: il database in uso è danneggiato. La copia
    nuova sarebbe danneggiata anche lei, quindi va buttata — e soprattutto i
    backup buoni di prima devono restare dove sono, perché sono l'unica via
    di scampo rimasta."""
    cartella_backup = tmp_path / "backup"
    cartella_backup.mkdir()
    monkeypatch.setattr(config, "DB_PATH", _db_danneggiato(tmp_path))
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella_backup)
    monkeypatch.setattr(config, "BACKUP_RETENZIONE_GIORNI", 30)
    monkeypatch.setattr(config, "BACKUP_MINIMI_DA_CONSERVARE", 0)

    buono_di_ieri = cartella_backup / "turni_2000-01-01_000000.db"
    buono_di_ieri.write_bytes(b"la copia buona di prima")
    vecchio_timestamp = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(buono_di_ieri, (vecchio_timestamp, vecchio_timestamp))

    assert backup.esegui_backup() is None
    # Nessuna copia nuova rimasta a fingersi valida...
    assert list(cartella_backup.iterdir()) == [buono_di_ieri]
    # ...e la pulizia per età non è nemmeno partita, benché il file superi la
    # retenzione: con il database rotto non si butta via l'ultima ancora.
    assert buono_di_ieri.exists()


def test_dopo_un_backup_fallito_non_si_ritenta_tutto_il_giorno(tmp_path, monkeypatch):
    """Il ciclo di sfondo chiama la funzione ogni minuto: senza memoria del
    fallimento, un database rotto farebbe ripartire una copia completa
    sessanta volte l'ora."""
    cartella_backup = tmp_path / "backup"
    monkeypatch.setattr(config, "DB_PATH", _db_danneggiato(tmp_path))
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella_backup)
    monkeypatch.setattr(config, "BACKUP_ABILITATO", True)
    monkeypatch.setattr(config, "BACKUP_ORA", "00:00")

    tentativi = []
    esegui_vero = backup.esegui_backup
    monkeypatch.setattr(backup, "esegui_backup", lambda: (tentativi.append(1), esegui_vero())[1])

    assert backup.controlla_e_backup_se_dovuto() is False
    assert backup.controlla_e_backup_se_dovuto() is False
    assert backup.controlla_e_backup_se_dovuto() is False
    assert len(tentativi) == 1


def test_la_retenzione_non_lascia_mai_la_cartella_senza_backup(tmp_path, monkeypatch):
    """Dopo un periodo di fermo tutti i backup superano la retenzione: le
    ultime copie vanno tenute lo stesso, altrimenti la cartella si svuota da
    sé proprio mentre nessuno stava guardando."""
    cartella_backup = tmp_path / "backup"
    cartella_backup.mkdir()
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella_backup)
    monkeypatch.setattr(config, "BACKUP_RETENZIONE_GIORNI", 30)
    monkeypatch.setattr(config, "BACKUP_MINIMI_DA_CONSERVARE", 3)

    creati = []
    for giorni in (90, 80, 70, 60, 50):
        p = cartella_backup / f"turni_2000-01-{giorni:02d}_000000.db"
        p.write_text("x")
        quando = (datetime.now() - timedelta(days=giorni)).timestamp()
        os.utime(p, (quando, quando))
        creati.append(p)

    backup._pulisci_backup_vecchi()

    rimasti = sorted(p.name for p in cartella_backup.iterdir())
    assert len(rimasti) == 3
    # Restano le tre più recenti (60, 50 giorni... cioè i giorni più bassi).
    assert rimasti == sorted(p.name for p in creati[2:])

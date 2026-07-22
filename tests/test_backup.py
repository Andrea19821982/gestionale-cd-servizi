import os
import sqlite3
from datetime import datetime, timedelta

from app import backup, config


def _db_di_prova(tmp_path):
    percorso = tmp_path / "turni.db"
    conn = sqlite3.connect(str(percorso))
    conn.execute("CREATE TABLE prova (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
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

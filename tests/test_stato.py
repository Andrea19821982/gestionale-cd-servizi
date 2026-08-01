"""Pagina Stato del programma (/stato)."""

import os
from datetime import datetime, timedelta

from app import config
from app.versione import VERSIONE
from tests.conftest import login


def _login(client, crea_utente, ruolo="amministratore"):
    crea_utente(f"utente_stato_{ruolo}", "passwordsegreta", ruolo)
    login(client, f"utente_stato_{ruolo}", "passwordsegreta")


def _finto_backup(cartella, nome, giorni_fa):
    cartella.mkdir(parents=True, exist_ok=True)
    percorso = cartella / nome
    percorso.write_text("x")
    quando = (datetime.now() - timedelta(days=giorni_fa)).timestamp()
    os.utime(percorso, (quando, quando))
    return percorso


def test_mostra_versione_e_archivio_integro(client, crea_utente, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_CARTELLA", tmp_path / "backup")
    _login(client, crea_utente)

    r = client.get("/stato")

    assert r.status_code == 200
    assert VERSIONE in r.text
    assert "Integro" in r.text


def test_avvisa_se_non_esiste_nessun_backup(client, crea_utente, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_CARTELLA", tmp_path / "backup_inesistente")
    _login(client, crea_utente)

    r = client.get("/stato")

    assert r.status_code == 200
    assert "nessuna copia di sicurezza" in r.text


def test_avvisa_se_l_ultimo_backup_e_vecchio(client, crea_utente, tmp_path, monkeypatch):
    cartella = tmp_path / "backup"
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella)
    _finto_backup(cartella, "turni_2026-01-01_030000.db", giorni_fa=10)
    _login(client, crea_utente)

    r = client.get("/stato")

    assert r.status_code == 200
    assert "risale a 10 giorni fa" in r.text


def test_un_backup_di_oggi_non_fa_scattare_nessun_avviso(client, crea_utente, tmp_path, monkeypatch):
    cartella = tmp_path / "backup"
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella)
    _finto_backup(cartella, "turni_2026-01-01_030000.db", giorni_fa=0)
    _login(client, crea_utente)

    r = client.get("/stato")

    assert r.status_code == 200
    assert "risale a" not in r.text
    assert "nessuna copia di sicurezza" not in r.text


def test_elenca_i_backup_dal_piu_recente(client, crea_utente, tmp_path, monkeypatch):
    cartella = tmp_path / "backup"
    monkeypatch.setattr(config, "BACKUP_CARTELLA", cartella)
    _finto_backup(cartella, "turni_vecchio_030000.db", giorni_fa=5)
    _finto_backup(cartella, "turni_recente_030000.db", giorni_fa=1)
    _login(client, crea_utente)

    r = client.get("/stato")

    assert r.text.index("turni_recente_030000.db") < r.text.index("turni_vecchio_030000.db")


def test_la_pagina_e_riservata_all_amministratore(client, crea_utente, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_CARTELLA", tmp_path / "backup")
    _login(client, crea_utente, ruolo="consultazione")

    assert client.get("/stato").status_code == 403


def test_la_voce_di_menu_la_vede_solo_l_amministratore(client, crea_utente, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_CARTELLA", tmp_path / "backup")
    _login(client, crea_utente, ruolo="gestore_turni")

    r = client.get("/calendario")

    assert r.status_code == 200
    assert 'href="/stato"' not in r.text

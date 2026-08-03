"""Segnale di arresto pulito del server (app/arresto.py).

È il meccanismo con cui l'installer spegne il server prima di sostituire i
file, al posto della chiusura forzata dal Task Manager.
"""

import sys
import threading

import pytest

from app import arresto

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="il segnale usa un evento di Windows")


def test_senza_nessun_server_in_esecuzione_non_finge_di_averlo_fermato():
    """Chi installa deve poter distinguere "fermato" da "non c'era niente da
    fermare": qui non c'è nessun evento creato, quindi la risposta è No."""
    assert arresto.chiedi_arresto() is False


def test_il_segnale_sblocca_chi_sta_aspettando():
    handle = arresto.crea_segnale()
    assert handle is not None

    arrivato = threading.Event()

    def _attendi():
        if arresto.attendi_segnale(handle):
            arrivato.set()

    thread = threading.Thread(target=_attendi, daemon=True)
    thread.start()

    assert arresto.chiedi_arresto() is True
    assert arrivato.wait(timeout=5), "il server non si è accorto della richiesta di arresto"
    thread.join(timeout=5)


def test_attendi_senza_segnale_non_esplode():
    """Se l'evento non si riesce a creare (sistemi diversi, permessi), il
    server deve continuare a funzionare: resta la chiusura dall'icona."""
    assert arresto.attendi_segnale(None) is False

"""Segnale di arresto pulito del server (app/arresto.py).

È il meccanismo con cui l'installer spegne il server prima di sostituire i
file, al posto della chiusura forzata dal Task Manager.

I test usano un nome di evento tutto loro: con quello vero dipenderebbero
da cosa sta girando sul PC e, soprattutto, finirebbero per spegnere il
server davvero in esecuzione — è successo alla prima stesura.
"""

import sys
import threading
import uuid

import pytest

from app import arresto

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="il segnale usa un evento di Windows")


@pytest.fixture
def nome_evento():
    return rf"Local\GestionaleCDServizi-Test-{uuid.uuid4().hex}"


def test_senza_nessun_server_in_esecuzione_non_finge_di_averlo_fermato(nome_evento):
    """Chi installa deve poter distinguere "fermato" da "non c'era niente da
    fermare": qui nessuno ha creato l'evento, quindi la risposta è No."""
    assert arresto.chiedi_arresto(nome_evento) is False


def test_il_segnale_sblocca_chi_sta_aspettando(nome_evento):
    handle = arresto.crea_segnale(nome_evento)
    assert handle is not None

    arrivato = threading.Event()

    def _attendi():
        if arresto.attendi_segnale(handle):
            arrivato.set()

    thread = threading.Thread(target=_attendi, daemon=True)
    thread.start()

    assert arresto.chiedi_arresto(nome_evento) is True
    assert arrivato.wait(timeout=5), "il server non si è accorto della richiesta di arresto"
    thread.join(timeout=5)


def test_attendi_senza_segnale_non_esplode():
    """Se l'evento non si riesce a creare (sistemi diversi, permessi), il
    server deve continuare a funzionare: resta la chiusura dall'icona."""
    assert arresto.attendi_segnale(None) is False


def test_il_nome_predefinito_e_quello_usato_da_server_e_installer():
    """Guardia: server e modalità --ferma devono parlarsi. Se il nome
    cambia da una parte sola, l'installer non riesce più a fermare il
    server e si torna al Task Manager senza che nessun test lo noti."""
    assert arresto.NOME_EVENTO == r"Local\GestionaleCDServizi-Arresto"

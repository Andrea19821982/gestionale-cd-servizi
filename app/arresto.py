"""Richiesta di arresto pulito del server, dall'esterno del programma.

Serve all'installer: prima di sostituire i file deve poter chiedere al
server in esecuzione di fermarsi da solo, invece di lasciare che sia
l'utente a terminarlo a forza dal Task Manager. Una chiusura forzata
lascia il file -wal non riassorbito accanto al database e obbliga chi
installa a ricordarsi un passaggio manuale proprio nel momento più
delicato: vedi _consolida_database in server_app.py.

Si usa un evento con nome di Windows invece di un endpoint HTTP di
spegnimento: il server ascolta su 0.0.0.0, quindi un comando del genere
sarebbe raggiungibile da tutti i PC dell'ufficio — una porta aperta che
nessuno ha chiesto. L'evento invece vive nella sessione dell'utente e non
esce dal PC.
"""

import sys

NOME_EVENTO = r"Local\GestionaleCDServizi-Arresto"

_SU_WINDOWS = sys.platform == "win32"

if _SU_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _EVENT_MODIFY_STATE = 0x0002
    _INFINITE = 0xFFFFFFFF
    _WAIT_OBJECT_0 = 0

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateEventW.restype = wintypes.HANDLE
    _kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.OpenEventW.restype = wintypes.HANDLE
    _kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    _kernel32.SetEvent.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD


def crea_segnale(nome: str = NOME_EVENTO):
    """Preparato dal server all'avvio. Restituisce un riferimento opaco da
    passare ad attendi_segnale, o None se il meccanismo non è disponibile
    (fuori da Windows, o se l'evento non si riesce a creare: in quel caso
    resta valida la chiusura dall'icona nella barra).

    Il nome si può cambiare solo per i test: usare quello vero li
    renderebbe dipendenti da cosa sta girando sul PC, e — peggio —
    un test finirebbe per spegnere il server davvero in esecuzione."""
    if not _SU_WINDOWS:
        return None
    handle = _kernel32.CreateEventW(None, True, False, nome)
    return handle or None


def attendi_segnale(handle) -> bool:
    """Si blocca finché qualcuno non chiede l'arresto. True se è arrivata
    davvero la richiesta."""
    if not _SU_WINDOWS or not handle:
        return False
    return _kernel32.WaitForSingleObject(handle, _INFINITE) == _WAIT_OBJECT_0


def chiedi_arresto(nome: str = NOME_EVENTO) -> bool:
    """Chiede al server in esecuzione di fermarsi. True se un server c'era
    ed è stato avvisato; False se non ne risulta nessuno in ascolto (che
    per chi installa è comunque una buona notizia: non c'è niente da
    chiudere)."""
    if not _SU_WINDOWS:
        return False
    handle = _kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, nome)
    if not handle:
        return False
    try:
        return bool(_kernel32.SetEvent(handle))
    finally:
        _kernel32.CloseHandle(handle)

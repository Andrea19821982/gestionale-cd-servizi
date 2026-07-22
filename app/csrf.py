"""Protezione CSRF con il pattern "double-submit cookie": ogni risposta
porta un cookie csrf_token (leggibile da pagina, non HttpOnly, ma NON
leggibile da un sito esterno per via della same-origin policy del browser);
ogni form POST include lo stesso valore in un campo nascosto. Una richiesta
falsificata da un altro sito farebbe arrivare il cookie (a meno di
SameSite), ma non potrebbe MAI leggerne il valore per copiarlo nel campo
nascosto: senza il valore giusto in entrambi i posti, la richiesta è
rifiutata.

Nessuno stato lato server: il cookie stesso è la fonte di verità, quindi
funziona identico dopo un riavvio del server o con più processi."""

import secrets

from fastapi import Form, HTTPException, Request

NOME_COOKIE_CSRF = "csrf_token"
DURATA_COOKIE_SECONDI = 60 * 60 * 24 * 30


def genera_token() -> str:
    return secrets.token_urlsafe(32)


def richiedi_csrf_valido(request: Request, csrf_token: str = Form(...)) -> None:
    """Dependency da aggiungere a ogni route POST/PUT/DELETE che modifica
    dati: confronta il token del form con quello del cookie della stessa
    richiesta. Usare compare_digest invece di == evita di far trapelare per
    quanti caratteri il confronto è arrivato (timing attack)."""
    atteso = request.cookies.get(NOME_COOKIE_CSRF)
    if not atteso or not secrets.compare_digest(csrf_token, atteso):
        raise HTTPException(
            status_code=403,
            detail="Richiesta non valida o sessione scaduta (protezione CSRF). Ricarica la pagina e riprova.",
        )

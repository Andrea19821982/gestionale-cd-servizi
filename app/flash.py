"""Messaggio "flash" minimo: un avviso salvato nella sessione da una route
che poi reindirizza altrove, mostrato una volta sola nella pagina successiva
e poi dimenticato (letto e rimosso dal middleware in main.py)."""

from fastapi import Request


def imposta_flash(request: Request, testo: str, tipo: str = "avviso") -> None:
    request.session["flash"] = {"testo": testo, "tipo": tipo}

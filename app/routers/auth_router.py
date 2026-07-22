from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import autentica, minuti_blocco_login_residui, registra_tentativo_login
from app.csrf import richiedi_csrf_valido
from app.database import get_db
from app.templates import templates

router = APIRouter()


def _next_sicuro(next: str) -> str:
    """"next" arriva da un parametro controllato da chi visita la pagina
    (query string o campo di form): senza questo controllo un link tipo
    /login?next=https://sito-finto.it reindirizzerebbe lì dopo un login
    riuscito (open redirect). Si accetta solo un percorso interno che inizia
    con un solo "/" (mai "//" o "/\", che i browser trattano come un
    indirizzo esterno)."""
    if next and next.startswith("/") and not next.startswith("//") and not next.startswith("/\\"):
        return next
    return "/"


@router.get("/login")
def mostra_login(request: Request, next: str = "/"):
    return templates.TemplateResponse(
        request, "login.html", {"next": _next_sicuro(next), "errore": None}
    )


@router.post("/login")
def esegui_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
    _csrf: None = Depends(richiedi_csrf_valido),
):
    next = _next_sicuro(next)
    username = username.strip()

    minuti_residui = minuti_blocco_login_residui(username)
    if minuti_residui > 0:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next,
                "errore": f"Troppi tentativi falliti per questo username: riprova tra {minuti_residui:.0f} minuti.",
            },
            status_code=429,
        )

    utente = autentica(db, username, password)
    registra_tentativo_login(username, riuscito=utente is not None)
    if utente is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "errore": "Username o password non corretti."},
            status_code=400,
        )
    request.session["utente_id"] = utente.id
    request.session["utente_ruolo"] = utente.ruolo
    request.session["utente_username"] = utente.username
    return RedirectResponse(next, status_code=303)


@router.post("/logout")
def esegui_logout(request: Request, _csrf: None = Depends(richiedi_csrf_valido)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

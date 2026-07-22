from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.paths import cartella_risorse

_RISORSE_DIR = cartella_risorse()

templates = Jinja2Templates(directory=str(_RISORSE_DIR / "templates"))

_STATIC_DIR = _RISORSE_DIR / "static"


def _versione_statico(nome_file: str) -> int:
    """Data di modifica del file statico, usata come query string per
    invalidare la cache del browser quando CSS/JS cambiano: evita di dover
    fare un refresh forzato manuale ogni volta che si aggiorna lo stile."""
    try:
        return int((_STATIC_DIR / nome_file).stat().st_mtime)
    except OSError:
        return 0


def _richieste_pendenti(request: Request) -> int:
    """Quante richieste di assenza aspettano una decisione: calcolato una
    volta per richiesta dal middleware in main.py (che usa la sessione DB
    corretta, compresa quella di test) e letto qui da request.state, usato
    dal banner di notifica in base.html su ogni pagina."""
    return getattr(request.state, "richieste_pendenti", 0)


def _bozze_email_pendenti(request: Request) -> int:
    """Quante bozze lette dalle email aspettano una conferma: stesso
    meccanismo di _richieste_pendenti sopra."""
    return getattr(request.state, "bozze_email_pendenti", 0)


def _csrf_token(request: Request) -> str:
    """Token CSRF della richiesta corrente (vedi app/csrf.py e il middleware
    gestisci_csrf in main.py), da mettere in un campo nascosto in ogni form
    POST."""
    return getattr(request.state, "csrf_token", "")


def _flash(request: Request) -> dict | None:
    """Messaggio flash consumato una sola volta (vedi app/flash.py): il
    middleware in main.py lo legge e lo toglie dalla sessione già prima che
    arrivi qui, quindi ricomparirà solo se impostato di nuovo da una route."""
    return getattr(request.state, "flash", None)


def _classe_nav_attiva(request: Request, prefisso: str) -> str:
    """Evidenzia nella barra di navigazione (base.html) il link della
    sezione in cui ci si trova: confronta per prefisso, non per uguaglianza
    esatta, così anche una sotto-pagina (es. /dipendenti/5/storico) evidenzia
    il link della sezione principale (/dipendenti)."""
    path = request.url.path
    if path == prefisso or path.startswith(prefisso + "/"):
        return "nav-link-attivo"
    return ""


templates.env.globals["versione_statico"] = _versione_statico
templates.env.globals["richieste_pendenti"] = _richieste_pendenti
templates.env.globals["bozze_email_pendenti"] = _bozze_email_pendenti
templates.env.globals["csrf_token"] = _csrf_token
templates.env.globals["flash"] = _flash
templates.env.globals["classe_nav_attiva"] = _classe_nav_attiva

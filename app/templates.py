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


def _palazzi_carenti(request: Request) -> list[str]:
    """Nomi dei palazzi/comparti sotto la copertura minima per domani (vedi
    app/allarme_copertura.py::blocchi_carenti), calcolato dallo stesso
    middleware di _richieste_pendenti sopra: un promemoria a monitor,
    indipendente dall'email dell'allarme di copertura, che chi gestisce i
    turni non deve arrivare a controllare la pagina Copertura per accorgersi
    di una carenza."""
    return getattr(request.state, "palazzi_carenti", [])


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


_PALETTE_AVATAR = ["#2563eb", "#7c3aed", "#db2777", "#d97706", "#0d9488", "#4338ca"]


def _iniziali(nome: str, cognome: str) -> str:
    """Iniziali cognome+nome per l'avatar (es. "Rossi Mario" -> "RM")."""
    lettera_cognome = cognome.strip()[0].upper() if cognome and cognome.strip() else ""
    lettera_nome = nome.strip()[0].upper() if nome and nome.strip() else ""
    return (lettera_cognome + lettera_nome) or "?"


def _colore_avatar(chiave: str) -> str:
    """Colore dalla palette categorica, deterministico per non cambiare
    a ogni ricarica della pagina (stessa persona -> stesso colore)."""
    indice = sum(ord(c) for c in chiave) % len(_PALETTE_AVATAR)
    return _PALETTE_AVATAR[indice]


def _colore_sequenziale(indice: int) -> str:
    """Colore dalla stessa palette categorica sopra, ma scelto per indice
    (in pratica l'id della riga) invece che con l'hash del testo: garantisce
    che elementi aggiunti in sequenza (es. un nuovo tipo turno) abbiano
    sempre un colore diverso dal precedente, a differenza di
    colore_avatar(etichetta) che può far collidere per caso due etichette
    diverse sullo stesso colore (successo prima con "Mattina" e
    "Pomeriggio", stessa somma di codici carattere modulo la lunghezza della
    palette)."""
    return _PALETTE_AVATAR[indice % len(_PALETTE_AVATAR)]


def _codice_turno(etichetta: str) -> str:
    """Abbreviazione compatta per la cella del calendario, troppo stretta
    per l'etichetta intera: M/P per i turni mattina/pomeriggio più comuni,
    INT per un turno intermedio, altrimenti le prime lettere dell'etichetta
    (i tipi turno sono liberi, configurabili in Tipi turno)."""
    e = (etichetta or "").strip().lower()
    if "mattin" in e:
        return "M"
    if "pomerig" in e:
        return "P"
    if "intermed" in e:
        return "INT"
    return (etichetta or "?")[:3].upper()


def _orario_breve(ora) -> str:
    """Ora senza i minuti se sono 00 (es. "7" invece di "7:00"), per stare
    nello spazio ridotto della cella del calendario."""
    return str(ora.hour) if ora.minute == 0 else f"{ora.hour}:{ora.minute:02d}"


def _orario_turno(tipo_turno) -> str:
    if tipo_turno is None:
        return ""
    return f"{_orario_breve(tipo_turno.ora_inizio)}-{_orario_breve(tipo_turno.ora_fine)}"


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
templates.env.globals["palazzi_carenti"] = _palazzi_carenti
templates.env.globals["csrf_token"] = _csrf_token
templates.env.globals["flash"] = _flash
templates.env.globals["classe_nav_attiva"] = _classe_nav_attiva
templates.env.globals["iniziali"] = _iniziali
templates.env.globals["colore_avatar"] = _colore_avatar
templates.env.globals["colore_sequenziale"] = _colore_sequenziale
templates.env.globals["codice_turno"] = _codice_turno
templates.env.globals["orario_turno"] = _orario_turno

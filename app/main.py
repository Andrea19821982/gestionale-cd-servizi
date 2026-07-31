import logging
import threading
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import email_config
from app.allarme_copertura import blocchi_carenti
from app.allarme_copertura import controlla_e_invia_se_dovuto as controlla_e_invia_allarme_copertura
from app.auth import NonAutenticato, puo_approvare_assenze
from app.backup import controlla_e_backup_se_dovuto
from app.config import SECRET_KEY
from app.csrf import DURATA_COOKIE_SECONDI, NOME_COOKIE_CSRF, genera_token
from app.database import get_db, init_db
from app.email_ingest import controlla_posta
from app.logging_service import configura_logging
from app.models import Assenza, BozzaEmail, Utente
from app.paths import cartella_risorse
from app.riepilogo_giornaliero import controlla_e_invia_se_dovuto
from app.routers import (
    allarme_copertura,
    area_personale,
    assenze,
    auth_router,
    bozze_email,
    calendario,
    copertura,
    dipendenti,
    esportazione,
    report,
    riepilogo_giornaliero,
    sale,
    sedi,
    sostituzioni,
    statistiche,
    tipi_turno,
    utenti,
)
from app.templates import templates

logger = logging.getLogger("calendario_turni.main")

_arresta_polling_posta = threading.Event()
_arresta_invio_riepilogo = threading.Event()
_arresta_allarme_copertura = threading.Event()
_arresta_backup = threading.Event()


def _ciclo_polling_posta():
    """Gira in un thread daemon per tutta la vita del processo: controlla la
    posta ogni IMAP_INTERVALLO_MINUTI minuti. Non deve mai far morire il
    thread per un errore imprevisto di una singola iterazione."""
    while not _arresta_polling_posta.wait(email_config.IMAP_INTERVALLO_MINUTI * 60):
        try:
            controlla_posta()
        except Exception:
            logger.exception("Ciclo di polling della posta: iterazione fallita")


def _ciclo_invio_riepilogo_giornaliero():
    """Controlla ogni minuto se è ora di mandare il riepilogo di domani:
    un intervallo breve perché l'orario configurato (RIEPILOGO_GIORNALIERO_ORA)
    va rispettato con precisione, non è un controllo pesante come la posta."""
    while not _arresta_invio_riepilogo.wait(60):
        controlla_e_invia_se_dovuto()  # non solleva mai eccezioni, vedi la funzione


def _ciclo_allarme_copertura():
    """Stesso schema del riepilogo giornaliero sopra, ma per il preavviso
    interno di carenza copertura (vedi app/allarme_copertura.py): un
    controllo al minuto per rispettare con precisione ALLARME_COPERTURA_ORA."""
    while not _arresta_allarme_copertura.wait(60):
        controlla_e_invia_allarme_copertura()  # non solleva mai eccezioni, vedi la funzione


def _ciclo_backup():
    """Stesso schema degli altri controlli periodici sopra, ma per il
    backup giornaliero del database (vedi app/backup.py)."""
    while not _arresta_backup.wait(60):
        controlla_e_backup_se_dovuto()  # non solleva mai eccezioni, vedi la funzione


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Per prima cosa: i cicli di sfondo avviati qui sotto registrano i loro
    # errori con logger.exception, e senza configurazione finirebbero su
    # stderr senza orario né provenienza (vedi configura_logging).
    configura_logging()
    init_db()
    # Sempre avviato (come gli altri cicli periodici sotto): la
    # configurazione IMAP può arrivare anche da /bozze-email dopo l'avvio
    # (vedi app/impostazioni_email.py), senza riavviare il programma.
    threading.Thread(target=_ciclo_polling_posta, daemon=True).start()
    threading.Thread(target=_ciclo_invio_riepilogo_giornaliero, daemon=True).start()
    threading.Thread(target=_ciclo_allarme_copertura, daemon=True).start()
    threading.Thread(target=_ciclo_backup, daemon=True).start()
    yield
    _arresta_polling_posta.set()
    _arresta_invio_riepilogo.set()
    _arresta_allarme_copertura.set()
    _arresta_backup.set()


app = FastAPI(title="Gestionale CD Servizi", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(cartella_risorse() / "static")), name="static")


@app.exception_handler(NonAutenticato)
def gestisci_non_autenticato(request: Request, exc: NonAutenticato):
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


TITOLI_ERRORE = {
    400: "Non è stato possibile salvare",
    403: "Non hai i permessi per questa operazione",
    404: "Pagina o dato non trovato",
}


@app.exception_handler(StarletteHTTPException)
async def gestisci_errore_http(request: Request, exc: StarletteHTTPException):
    """Mostra gli errori in una pagina leggibile invece che come JSON grezzo.

    I router sollevano HTTPException con messaggi scritti apposta in italiano
    semplice ("Il dipendente ha già un'assenza che si sovrappone a questo
    periodo"), ma i form sono POST normali: il browser NAVIGAVA sulla
    risposta di default di FastAPI, cioè {"detail": "..."}. L'utente si
    ritrovava una schermata bianca con del testo tecnico, senza menu e senza
    un modo ovvio di tornare al form — per un errore di tutti i giorni, come
    due date che si sovrappongono.

    Il codice di stato NON cambia: resta 400/403/404 esattamente come prima.
    Cambia solo la forma della risposta, a seconda di chi l'ha chiesta:
    - htmx: solo il testo, che il gestore globale in base.html mostra in un
      banner senza ricaricare la pagina;
    - navigazione del browser (Accept: text/html): errore.html, con il
      layout e il menu dell'applicazione;
    - tutto il resto: il JSON di sempre.
    """
    if request.headers.get("HX-Request"):
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request,
            "errore.html",
            {
                "titolo": TITOLI_ERRORE.get(exc.status_code, "Si è verificato un errore"),
                "messaggio": exc.detail,
            },
            status_code=exc.status_code,
        )

    return await http_exception_handler(request, exc)


@app.middleware("http")
async def calcola_richieste_pendenti(request: Request, call_next):
    """Precalcola per il banner in base.html quante richieste di assenza
    attendono una decisione. Passa dalla stessa dependency get_db (rispettando
    l'override usato dai test) invece di aprire una sessione diretta sul
    database reale, che romperebbe l'isolamento dei test. Registrato DOPO
    SessionMiddleware qui sotto: in Starlette l'ultimo middleware aggiunto è
    il più esterno ed è eseguito per primo, quindi va aggiunto SessionMiddleware
    per ultimo perché request.session sia già disponibile qui.

    Ne approfitta anche per tenere allineato session["utente_ruolo"] (letto
    da base.html per decidere le voci di menu da mostrare) con il ruolo
    attuale sul database: senza questo aggiornamento, un utente con una
    sessione già aperta il cui ruolo viene cambiato da un amministratore
    vedrebbe un menu basato sul ruolo ormai scaduto di quando ha fatto
    login, finché non rifà il login. I permessi veri restano comunque
    sempre quelli verificati da richiedi_ruolo sul database ad ogni
    richiesta: qui si aggiorna solo cosa viene mostrato nel menu."""
    request.state.richieste_pendenti = 0
    request.state.bozze_email_pendenti = 0
    request.state.palazzi_carenti = []
    request.state.flash = request.session.pop("flash", None)
    utente_id = request.session.get("utente_id")
    if utente_id is not None:
        db_factory = app.dependency_overrides.get(get_db, get_db)
        gen = db_factory()
        db = next(gen)
        try:
            utente = db.get(Utente, utente_id)
            if utente is not None and utente.attivo:
                request.session["utente_ruolo"] = utente.ruolo
                if puo_approvare_assenze(db, utente):
                    request.state.richieste_pendenti = db.query(Assenza).filter(Assenza.stato == "richiesta").count()
                if utente.ruolo in ("amministratore", "gestore_turni"):
                    request.state.bozze_email_pendenti = db.query(BozzaEmail).filter(BozzaEmail.stato == "da_confermare").count()
                    domani = date.today() + timedelta(days=1)
                    request.state.palazzi_carenti = [
                        blocco["nome_visualizzato"] for blocco in blocchi_carenti(db, domani)
                    ]
        finally:
            next(gen, None)
    return await call_next(request)


@app.middleware("http")
async def gestisci_csrf(request: Request, call_next):
    """Garantisce che ogni richiesta abbia un cookie csrf_token (double-submit,
    vedi app/csrf.py): lo legge se già presente, altrimenti lo genera e lo
    espone in request.state per il template corrente, impostandolo sulla
    risposta solo se non c'era già (evita di riscriverlo a ogni richiesta)."""
    token_esistente = request.cookies.get(NOME_COOKIE_CSRF)
    request.state.csrf_token = token_esistente or genera_token()
    response = await call_next(request)
    if not token_esistente:
        response.set_cookie(
            NOME_COOKIE_CSRF, request.state.csrf_token,
            httponly=False, samesite="lax", max_age=DURATA_COOKIE_SECONDI,
        )
    return response


app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.get("/")
def index():
    return RedirectResponse("/calendario")


app.include_router(auth_router.router)
app.include_router(allarme_copertura.router)
app.include_router(sedi.router)
app.include_router(sale.router)
app.include_router(tipi_turno.router)
app.include_router(dipendenti.router)
app.include_router(calendario.router)
app.include_router(assenze.router)
app.include_router(sostituzioni.router)
app.include_router(esportazione.router)
app.include_router(statistiche.router)
app.include_router(utenti.router)
app.include_router(area_personale.router)
app.include_router(copertura.router)
app.include_router(report.router)
app.include_router(bozze_email.router)
app.include_router(riepilogo_giornaliero.router)

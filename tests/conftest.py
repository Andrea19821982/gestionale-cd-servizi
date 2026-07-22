import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import Utente


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test_turni.db"
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def db(SessionTest):
    session = SessionTest()
    yield session
    session.close()


@pytest.fixture
def client(SessionTest):
    # Niente "with": evita che parta il lifespan/startup di app.main (che
    # inizializzerebbe il database reale del progetto invece di quello di test).
    def override_get_db():
        session = SessionTest()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)

    # Ogni form POST ora richiede un token CSRF valido (vedi app/csrf.py):
    # invece di aggiungerlo a mano in ognuno dei tanti client.post() già
    # scritti nei test, lo si inietta automaticamente qui, leggendolo dal
    # cookie che il server imposta alla prima richiesta (esattamente come
    # farebbe un vero browser). Un test che vuole verificare il rifiuto di un
    # token sbagliato/mancante può comunque passare "csrf_token" esplicito in
    # data: quello scritto a mano vince sempre su quello automatico.
    post_originale = test_client.post

    def post_con_csrf(url, *args, **kwargs):
        token = test_client.cookies.get("csrf_token")
        if not token:
            test_client.get("/login")
            token = test_client.cookies.get("csrf_token", "")
        dati = kwargs.get("data")
        if dati is None:
            kwargs["data"] = {"csrf_token": token}
        elif "csrf_token" not in dati:
            kwargs["data"] = {**dati, "csrf_token": token}
        return post_originale(url, *args, **kwargs)

    test_client.post = post_con_csrf
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _pulisci_tentativi_login():
    """Il contatore anti-bruteforce del login (app/auth.py) è un dict a
    livello di modulo, condiviso tra tutti i test dello stesso processo
    pytest: senza questo reset, un test che genera troppi fallimenti per uno
    username potrebbe far scattare un blocco inatteso in un test successivo
    che riusa lo stesso username per un login legittimo."""
    from app.auth import _tentativi_falliti

    _tentativi_falliti.clear()
    yield
    _tentativi_falliti.clear()


@pytest.fixture
def crea_utente(db):
    def _crea(username, password, ruolo):
        utente = Utente(
            username=username,
            password_hash=hash_password(password),
            ruolo=ruolo,
            attivo=True,
        )
        db.add(utente)
        db.commit()
        db.refresh(utente)
        return utente

    return _crea


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )

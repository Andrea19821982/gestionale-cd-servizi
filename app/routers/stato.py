"""Stato del programma: versione, salute del database, copie di sicurezza.

Serve a rendere visibile ciò che finora si poteva sapere solo aprendo le
cartelle di sistema. Un database danneggiato o un backup che ha smesso di
essere fatto non si annunciano da soli: ce ne si accorge il giorno in cui
serviva il backup, cioè troppo tardi. Qui si vedono a colpo d'occhio, e
solo l'amministratore può guardarli (dicono percorsi e stato interno).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import config
from app.auth import RUOLI_SCRITTURA_ANAGRAFICA, richiedi_ruolo
from app.database import get_db, verifica_integrita
from app.models import Utente
from app.templates import templates
from app.versione import VERSIONE

router = APIRouter()

# Oltre questi giorni senza una copia nuova, la pagina lo segnala: il backup
# si fa solo a server acceso, quindi "nessun backup recente" di solito vuol
# dire che il server è rimasto spento, non che il backup è rotto — ma in
# entrambi i casi è bene saperlo prima che serva.
GIORNI_PRIMA_DI_SEGNALARE = 3


def _dimensione_leggibile(byte: int) -> str:
    if byte < 1024 * 1024:
        return f"{byte / 1024:.0f} KB"
    return f"{byte / (1024 * 1024):.1f} MB"


def _elenco_backup() -> list[dict]:
    if not config.BACKUP_CARTELLA.exists():
        return []
    trovati = []
    for percorso in config.BACKUP_CARTELLA.glob("turni_*.db"):
        try:
            stato = percorso.stat()
        except OSError:
            continue
        trovati.append({
            "nome": percorso.name,
            "quando": datetime.fromtimestamp(stato.st_mtime),
            "dimensione": _dimensione_leggibile(stato.st_size),
        })
    return sorted(trovati, key=lambda b: b["quando"], reverse=True)


@router.get("/stato")
def stato_programma(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(richiedi_ruolo(*RUOLI_SCRITTURA_ANAGRAFICA)),
):
    backup = _elenco_backup()
    ultimo = backup[0] if backup else None
    giorni_dall_ultimo = (datetime.now() - ultimo["quando"]).days if ultimo else None

    try:
        dimensione_database = _dimensione_leggibile(config.DB_PATH.stat().st_size)
    except OSError:
        dimensione_database = "—"

    return templates.TemplateResponse(
        request,
        "stato.html",
        {
            "utente": utente,
            "versione": VERSIONE,
            "problema_database": verifica_integrita(),
            "percorso_database": str(config.DB_PATH),
            "dimensione_database": dimensione_database,
            "cartella_backup": str(config.BACKUP_CARTELLA),
            "backup": backup[:10],
            "numero_backup": len(backup),
            "ultimo_backup": ultimo,
            "giorni_dall_ultimo_backup": giorni_dall_ultimo,
            "giorni_prima_di_segnalare": GIORNI_PRIMA_DI_SEGNALARE,
            "backup_abilitato": config.BACKUP_ABILITATO,
            "ora_backup": config.BACKUP_ORA,
            "retenzione_giorni": config.BACKUP_RETENZIONE_GIORNI,
            "minimi_da_conservare": config.BACKUP_MINIMI_DA_CONSERVARE,
        },
    )

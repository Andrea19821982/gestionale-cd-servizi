import secrets

from app.paths import cartella_dati

DB_PATH = cartella_dati() / "turni.db"

# --- Backup automatico giornaliero del database ---
# Una copia di sicurezza al giorno, con l'API di backup di sqlite3 (sicura
# anche a database aperto): protegge dal caso limite, ma reale per un unico
# file SQLite su un solo PC, di un disco che si guasta o di un file
# danneggiato. Vedi app/backup.py.

BACKUP_ABILITATO = True
BACKUP_ORA = "03:00"  # un orario tranquillo: pochi turni vengono registrati di notte
BACKUP_RETENZIONE_GIORNI = 30
BACKUP_CARTELLA = cartella_dati() / "backup"


def _secret_key_persistente() -> str:
    """Chiave di firma del cookie di sessione: generata automaticamente al
    primo avvio (casuale, unica per questa installazione) e salvata in un
    file accanto al database, così non serve nessuna configurazione manuale
    e non c'è mai una chiave uguale su installazioni diverse. Cancellare
    questo file invalida tutte le sessioni attive (tutti dovranno rifare il
    login) ma non è un problema di sicurezza: ne verrà generata una nuova."""
    percorso = cartella_dati() / "secret_key.txt"
    if percorso.exists():
        chiave = percorso.read_text(encoding="utf-8").strip()
        if chiave:
            return chiave
    chiave = secrets.token_hex(32)
    percorso.write_text(chiave, encoding="utf-8")
    return chiave


SECRET_KEY = _secret_key_persistente()

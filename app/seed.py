"""Dati di sviluppo: sedi, tipi turno, utenti e dipendenti fittizi.

Nessun nominativo reale: i nomi veri del personale restano solo nel file
Excel originale di Andrea (regola vincolante 4). Questo script serve per
poter usare e testare l'applicazione senza quei dati.

Uso:
    python -m app.seed
"""

from datetime import time

from app.auth import hash_password
from app.database import SessionLocal, init_db
from app.models import Dipendente, Sala, Sede, TipoTurno, Utente

SEDI = [
    ("Montecitorio", "#e8622c"),
    ("Valdina", "#29abe2"),
    ("Ex Banco di Napoli", "#7cb342"),
    ("Seminario", "#6c5ce7"),
    ("Theodoli", "#d6336c"),
    ("Palazzo dei Gruppi", "#f0a202"),
    ("Palazzo San Macuto", "#00838f"),
]

# Sale per eventi dentro i palazzi sopra: quando è in programma un evento
# (vedi app/routers/sale.py) la copertura minima richiesta per il palazzo
# sale di "copertura_minima_aggiuntiva". Numero di partenza, da correggere
# dall'amministratore nella pagina "Sale" appena si conoscono i valori reali.
SALE = [
    ("Sala del Mappamondo", "Montecitorio", 1),
    ("Sala della Lupa", "Montecitorio", 1),
    ("Sala della Regina", "Montecitorio", 1),
    ("Sala Stampa", "Montecitorio", 1),
    ("Nuova Aula dei Gruppi Parlamentari", "Palazzo dei Gruppi", 1),
    ("Sala della Sacrestia", "Valdina", 1),
    ("Sala del Cenacolo", "Valdina", 1),
    ("Sala del Refettorio", "Palazzo San Macuto", 1),
    ("Sala Matteotti", "Theodoli", 1),
]

TIPI_TURNO = [
    ("Mattina", time(7, 0), time(13, 30)),
    ("Pomeriggio", time(13, 30), time(20, 0)),
    ("Pomeriggio lungo", time(14, 30), time(21, 0)),
]

UTENTI = [
    ("admin", "admin1234", "amministratore"),
    ("gestore", "gestore1234", "gestore_turni"),
    ("consultazione", "consultazione1234", "consultazione"),
]

DIPENDENTI_FITTIZI = [
    ("Bianchi Test", "Mario", "Montecitorio"),
    ("Verdi Test", "Luca", "Valdina"),
    ("Neri Test", "Anna", "Seminario"),
    ("Rossi Test", "Giulia", "Ex Banco di Napoli"),
    ("Russo Test", "Paolo", "Theodoli"),
]


def _get_or_create(db, modello, filtro, valori):
    istanza = db.query(modello).filter_by(**filtro).first()
    if istanza:
        return istanza, False
    istanza = modello(**valori)
    db.add(istanza)
    db.flush()
    return istanza, True


def semina():
    init_db()
    db = SessionLocal()
    try:
        sedi_per_nome = {}
        for nome, colore in SEDI:
            sede, creata = _get_or_create(
                db, Sede, {"nome": nome}, {"nome": nome, "colore_hex": colore, "attivo": True}
            )
            sedi_per_nome[nome] = sede
            print(f"{'creata' if creata else 'già presente'}: sede {nome}")

        for nome, sede_nome, copertura_aggiuntiva in SALE:
            _, creata = _get_or_create(
                db,
                Sala,
                {"nome": nome},
                {
                    "nome": nome,
                    "sede_id": sedi_per_nome[sede_nome].id,
                    "copertura_minima_aggiuntiva": copertura_aggiuntiva,
                    "attivo": True,
                },
            )
            print(f"{'creata' if creata else 'già presente'}: sala {nome} ({sede_nome})")

        for etichetta, inizio, fine in TIPI_TURNO:
            _, creato = _get_or_create(
                db,
                TipoTurno,
                {"etichetta": etichetta},
                {"etichetta": etichetta, "ora_inizio": inizio, "ora_fine": fine},
            )
            print(f"{'creato' if creato else 'già presente'}: tipo turno {etichetta}")

        for username, password, ruolo in UTENTI:
            _, creato = _get_or_create(
                db,
                Utente,
                {"username": username},
                {
                    "username": username,
                    "password_hash": hash_password(password),
                    "ruolo": ruolo,
                    "attivo": True,
                },
            )
            print(f"{'creato' if creato else 'già presente'}: utente {username} ({ruolo})")

        primo_dipendente = None
        for cognome, nome, sede_nome in DIPENDENTI_FITTIZI:
            dip, creato = _get_or_create(
                db,
                Dipendente,
                {"cognome": cognome, "nome": nome},
                {
                    "cognome": cognome,
                    "nome": nome,
                    "sede_riferimento_id": sedi_per_nome[sede_nome].id,
                    "ordine_visualizzazione": 0,
                    "attivo": True,
                },
            )
            if primo_dipendente is None:
                primo_dipendente = dip
            print(f"{'creato' if creato else 'già presente'}: dipendente {cognome} {nome}")

        # Account di esempio per l'area personale self-service (ruolo "dipendente"),
        # collegato al primo dipendente fittizio.
        _, creato = _get_or_create(
            db,
            Utente,
            {"username": "dipendente"},
            {
                "username": "dipendente",
                "password_hash": hash_password("dipendente1234"),
                "ruolo": "dipendente",
                "dipendente_collegato_id": primo_dipendente.id,
                "attivo": True,
            },
        )
        print(f"{'creato' if creato else 'già presente'}: utente dipendente (dipendente, collegato a {primo_dipendente.cognome} {primo_dipendente.nome})")

        db.commit()
        print("\nCredenziali di sviluppo (username / password):")
        for username, password, ruolo in UTENTI:
            print(f"  {username} / {password}  -> {ruolo}")
        print("  dipendente / dipendente1234  -> dipendente (area personale self-service)")
    finally:
        db.close()


if __name__ == "__main__":
    semina()

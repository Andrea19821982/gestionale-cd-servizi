from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

RUOLI_VALIDI = ("amministratore", "gestore_turni", "consultazione", "dipendente")
ORIGINI_VALIDE = ("pattern", "manuale", "sostituzione", "assenza")
AZIONI_VALIDE = ("creazione", "modifica", "cancellazione")
STATI_ASSENZA_VALIDI = ("richiesta", "approvata", "rifiutata")
TIPI_BOZZA_EMAIL_VALIDI = ("assenza", "sostituzione")
STATI_BOZZA_EMAIL_VALIDI = ("da_confermare", "confermata", "scartata")


class Sede(Base):
    __tablename__ = "sedi"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    colore_hex: Mapped[str] = mapped_column(String, nullable=False)
    attivo: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Sostituita da copertura_minima_mattina/pomeriggio sotto (la copertura
    # minima ora si valuta separatamente per le due fasce, non più su tutta
    # la giornata insieme): rimane in tabella solo perché SQLite prima della
    # 3.35 non rimuove colonne facilmente, ma non è più letta da nessuna
    # query — vedi _migra_schema in app/database.py per come sono stati
    # riportati i valori esistenti nelle due colonne nuove.
    copertura_minima_ordinaria: Mapped[int] = mapped_column(default=0, nullable=False)
    # Numero minimo di persone richieste nella fascia di mattina/pomeriggio
    # per il solo funzionamento ordinario del palazzo, a prescindere da
    # eventi nelle sale (vedi Sala sotto). 0 = non ancora configurato
    # dall'amministratore. La fascia di un turno è TipoTurno.fascia.
    copertura_minima_mattina: Mapped[int] = mapped_column(default=0, nullable=False)
    copertura_minima_pomeriggio: Mapped[int] = mapped_column(default=0, nullable=False)
    # Ordine con cui il palazzo compare nel cruscotto Copertura (e nel
    # riepilogo giornaliero via email, che usa la stessa query): a parità di
    # valore si ordina per nome. Impostabile da Sedi.
    ordine_visualizzazione: Mapped[int] = mapped_column(default=0, nullable=False)


class SottosezioneCopertura(Base):
    """Copertura minima propria per un comparto (Dipendente.sottosezione,
    es. "Parcheggio" dentro Valdina): stesso principio di Sede sopra, ma per
    un sottoinsieme di dipendenti della sede che va monitorato a parte
    invece che insieme al resto del palazzo (vedi
    app/routers/copertura.py::calcola_copertura). "nome" deve corrispondere
    esattamente al testo scritto in Dipendente.sottosezione: non è una
    chiave esterna verso una tabella di dipendenti perché sottosezione resta
    un campo libero, non un elenco chiuso."""
    __tablename__ = "sottosezioni_copertura"
    __table_args__ = (
        UniqueConstraint("sede_id", "nome", name="uq_sottosezione_copertura_sede_nome"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedi.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    copertura_minima_mattina: Mapped[int] = mapped_column(default=0, nullable=False)
    copertura_minima_pomeriggio: Mapped[int] = mapped_column(default=0, nullable=False)

    sede: Mapped[Sede] = relationship()


class Sala(Base):
    """Una sala per eventi dentro un palazzo (es. Sala della Lupa dentro
    Montecitorio): quando c'è un evento in programma (vedi EventoSala) serve
    una copertura aggiuntiva rispetto a quella ordinaria del palazzo."""
    __tablename__ = "sale"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedi.id"), nullable=False)
    copertura_minima_aggiuntiva: Mapped[int] = mapped_column(default=1, nullable=False)
    attivo: Mapped[bool] = mapped_column(default=True, nullable=False)

    sede: Mapped[Sede] = relationship()


class EventoSala(Base):
    """Un evento programmato in una sala in un intervallo di date: finché è
    in corso, la copertura minima richiesta per il palazzo della sala sale
    di sala.copertura_minima_aggiuntiva (vedi calcola_copertura)."""
    __tablename__ = "eventi_sala"

    id: Mapped[int] = mapped_column(primary_key=True)
    sala_id: Mapped[int] = mapped_column(ForeignKey("sale.id"), nullable=False)
    data_inizio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fine: Mapped[date] = mapped_column(Date, nullable=False)
    descrizione: Mapped[str | None] = mapped_column(String, nullable=True)
    creato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)
    creato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    sala: Mapped[Sala] = relationship()


class Dipendente(Base):
    __tablename__ = "dipendenti"

    id: Mapped[int] = mapped_column(primary_key=True)
    cognome: Mapped[str] = mapped_column(String, nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    # Indirizzo email personale del dipendente: facoltativo (molti dipendenti
    # potrebbero non averlo mai compilato), usato solo per inoltrare loro i
    # moduli di segnalazione assenze/sostituzioni (vedi /bozze-email).
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    sede_riferimento_id: Mapped[int | None] = mapped_column(
        ForeignKey("sedi.id"), nullable=True
    )
    ordine_visualizzazione: Mapped[int] = mapped_column(default=0, nullable=False)
    attivo: Mapped[bool] = mapped_column(default=True, nullable=False)
    giorni_ferie_annuali: Mapped[int] = mapped_column(default=26, nullable=False)
    tipo_contratto: Mapped[str | None] = mapped_column(String, nullable=True)
    # Ore settimanali previste dal contratto: 40 = tempo pieno, un valore
    # minore prorata automaticamente ferie annuali e ore mensili attese
    # (vedi statistiche._ferie_annuali_effettive / _ore_contrattuali_nel_mese).
    ore_settimanali_contrattuali: Mapped[float] = mapped_column(default=40.0, nullable=False)
    costo_orario: Mapped[float | None] = mapped_column(nullable=True)
    # Raggruppamento libero all'interno della sede (es. "Parcheggio",
    # "Archivio legislativo"): chi ce l'ha valorizzato viene mostrato nel
    # calendario in una sezione separata, staccata dagli altri dipendenti
    # della stessa sede ma nella stessa pagina (vedi
    # app/routers/calendario.py::_raggruppa_per_sottosezione). None = nessun
    # raggruppamento, mostrato come oggi insieme a tutti gli altri.
    sottosezione: Mapped[str | None] = mapped_column(String, nullable=True)

    sede_riferimento: Mapped[Sede | None] = relationship()


FASCE_TURNO_VALIDE = ("mattina", "pomeriggio", "entrambe")


class TipoTurno(Base):
    __tablename__ = "tipi_turno"
    __table_args__ = (
        CheckConstraint(f"fascia IS NULL OR fascia IN {FASCE_TURNO_VALIDE}", name="ck_tipi_turno_fascia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    etichetta: Mapped[str] = mapped_column(String, nullable=False)
    ora_inizio: Mapped[time] = mapped_column(Time, nullable=False)
    ora_fine: Mapped[time] = mapped_column(Time, nullable=False)
    # A quale fascia appartiene questo turno, per il conteggio della
    # copertura minima mattina/pomeriggio (vedi Sede.copertura_minima_mattina
    # sopra e calcola_copertura in app/routers/copertura.py): impostato
    # esplicitamente dall'amministratore in Tipi turno, mai dedotto in
    # automatico dall'orario, perché un turno come "Pomeriggio lungo"
    # (14:30-21:00) o uno importato con orari intermedi non ha una fascia
    # ovvia da un semplice confronto sull'ora di inizio. "entrambe" è per un
    # turno che copre parte di entrambe le fasce (es. un intermedio
    # 11:00-17:30): chi lo fa risulta presente sia per il minimo mattina sia
    # per quello pomeriggio. None = non ancora classificato: quel turno non
    # entra nel conteggio di nessuna fascia finché l'amministratore non lo
    # imposta (vedi l'avviso in copertura.html).
    fascia: Mapped[str | None] = mapped_column(String, nullable=True)


class PatternTurno(Base):
    __tablename__ = "pattern_turno"

    dipendente_id: Mapped[int] = mapped_column(
        ForeignKey("dipendenti.id"), primary_key=True
    )
    turno_settimana_dispari_id: Mapped[int | None] = mapped_column(
        ForeignKey("tipi_turno.id"), nullable=True
    )
    turno_settimana_pari_id: Mapped[int | None] = mapped_column(
        ForeignKey("tipi_turno.id"), nullable=True
    )


class AssegnazioneGiornaliera(Base):
    __tablename__ = "assegnazioni_giornaliere"
    __table_args__ = (
        CheckConstraint(f"origine IN {ORIGINI_VALIDE}", name="ck_assegnazioni_origine"),
        UniqueConstraint("dipendente_id", "data", name="uq_assegnazioni_dipendente_data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dipendente_id: Mapped[int] = mapped_column(ForeignKey("dipendenti.id"), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    sede_effettiva_id: Mapped[int] = mapped_column(ForeignKey("sedi.id"), nullable=False)
    tipo_turno_id: Mapped[int | None] = mapped_column(
        ForeignKey("tipi_turno.id"), nullable=True
    )
    origine: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cosa c'era prima che un'assenza coprisse questo giorno. Un'assenza
    # approvata sovrascrive il turno — essere assenti prevale su quanto
    # pianificato — ma se poi viene rifiutata o cancellata il turno di prima
    # va restituito. Senza queste due colonne veniva perso per sempre,
    # insieme al lavoro di chi aveva pianificato la copertura a mano, e
    # nemmeno il registro delle modifiche lo conservava. Restano NULL su
    # tutte le righe che nessuna assenza ha mai toccato.
    tipo_turno_precedente_id: Mapped[int | None] = mapped_column(
        ForeignKey("tipi_turno.id"), nullable=True
    )
    origine_precedente: Mapped[str | None] = mapped_column(String, nullable=True)

    # foreign_keys esplicito: con due colonne che puntano entrambe a
    # tipi_turno, SQLAlchemy non può indovinare da sola quale usare.
    tipo_turno: Mapped[TipoTurno | None] = relationship(foreign_keys=[tipo_turno_id])
    sede_effettiva: Mapped[Sede] = relationship()


class Assenza(Base):
    __tablename__ = "assenze"
    __table_args__ = (
        CheckConstraint(f"stato IN {STATI_ASSENZA_VALIDI}", name="ck_assenze_stato"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dipendente_id: Mapped[int] = mapped_column(ForeignKey("dipendenti.id"), nullable=False)
    data_inizio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fine: Mapped[date] = mapped_column(Date, nullable=False)
    tipo_assenza: Mapped[str] = mapped_column(String, nullable=False)
    # richiesta = appena registrata, non ancora effettiva sul calendario;
    # approvata = copre le celle del calendario; rifiutata = non le tocca.
    stato: Mapped[str] = mapped_column(String, default="richiesta", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    creato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)
    creato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    deciso_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)
    deciso_il: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Nome del file come caricato dall'utente (mostrato nei link) e percorso
    # relativo dentro cartella_dati()/allegati dove è stato salvato davvero.
    allegato_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    allegato_path: Mapped[str | None] = mapped_column(String, nullable=True)

    dipendente: Mapped[Dipendente] = relationship()


class Sostituzione(Base):
    __tablename__ = "sostituzioni"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    dipendente_partente_id: Mapped[int] = mapped_column(
        ForeignKey("dipendenti.id"), nullable=False
    )
    sede_partenza_id: Mapped[int] = mapped_column(ForeignKey("sedi.id"), nullable=False)
    dipendente_sostituto_id: Mapped[int] = mapped_column(
        ForeignKey("dipendenti.id"), nullable=False
    )
    sede_arrivo_id: Mapped[int] = mapped_column(ForeignKey("sedi.id"), nullable=False)
    # Entrambi nulli = sostituzione per l'intera giornata. Valorizzati =
    # sostituzione solo per quella fascia oraria (es. 1-2 ore): il calendario
    # in quel caso non sostituisce la cella, mostra solo un indicatore.
    ora_inizio: Mapped[time | None] = mapped_column(Time, nullable=True)
    ora_fine: Mapped[time | None] = mapped_column(Time, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    creato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)
    creato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    dipendente_partente: Mapped[Dipendente] = relationship(foreign_keys=[dipendente_partente_id])
    dipendente_sostituto: Mapped[Dipendente] = relationship(foreign_keys=[dipendente_sostituto_id])
    sede_partenza: Mapped[Sede] = relationship(foreign_keys=[sede_partenza_id])
    sede_arrivo: Mapped[Sede] = relationship(foreign_keys=[sede_arrivo_id])


class DelegaApprovazione(Base):
    """Delega temporanea del potere di approvare/rifiutare le assenze a un
    utente che non è amministratore (es. il capo è assente per ferie): copre
    solo l'intervallo data_inizio..data_fine, oltre resta senza effetto."""
    __tablename__ = "deleghe_approvazione"

    id: Mapped[int] = mapped_column(primary_key=True)
    utente_delegato_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"), nullable=False)
    data_inizio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fine: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    creato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)
    creato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    utente_delegato: Mapped["Utente"] = relationship(foreign_keys=[utente_delegato_id])


class Utente(Base):
    __tablename__ = "utenti"
    __table_args__ = (
        CheckConstraint(f"ruolo IN {RUOLI_VALIDI}", name="ck_utenti_ruolo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    ruolo: Mapped[str] = mapped_column(String, nullable=False)
    dipendente_collegato_id: Mapped[int | None] = mapped_column(
        ForeignKey("dipendenti.id"), nullable=True
    )
    attivo: Mapped[bool] = mapped_column(default=True, nullable=False)

    dipendente_collegato: Mapped[Dipendente | None] = relationship()


class BozzaEmail(Base):
    """Assenza o sostituzione letta automaticamente da un'email dei
    dipendenti (vedi app/email_ingest.py): resta "da_confermare" finché un
    amministrativo non la rivede e conferma (crea la vera Assenza/Sostituzione)
    o la scarta. Non tocca mai il calendario da sola."""
    __tablename__ = "bozze_email"
    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPI_BOZZA_EMAIL_VALIDI}", name="ck_bozze_email_tipo"),
        CheckConstraint(f"stato IN {STATI_BOZZA_EMAIL_VALIDI}", name="ck_bozze_email_stato"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    stato: Mapped[str] = mapped_column(String, default="da_confermare", nullable=False)

    # Dati grezzi dell'email originale, per poter sempre ricontrollare a mano
    # cosa è stato scritto davvero se l'interpretazione automatica sbaglia.
    mittente: Mapped[str] = mapped_column(String, nullable=False)
    oggetto: Mapped[str] = mapped_column(String, nullable=False)
    corpo: Mapped[str] = mapped_column(Text, nullable=False)
    ricevuta_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    # Se non tutto è stato interpretato con certezza (dipendente non trovato
    # o ambiguo, data non valida, campo mancante), qui c'è scritto cosa
    # controllare: la bozza viene comunque creata, mai scartata in silenzio.
    errore_parsing: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Campi interpretati dal corpo dell'email. Per "assenza": dipendente_id,
    # tipo_assenza, data_inizio, data_fine, note. Per "sostituzione":
    # dipendente_id (l'assente), dipendente_sostituto_id, data_inizio (unica
    # data), ora_inizio/ora_fine (nulli = intera giornata).
    dipendente_id: Mapped[int | None] = mapped_column(ForeignKey("dipendenti.id"), nullable=True)
    dipendente_sostituto_id: Mapped[int | None] = mapped_column(ForeignKey("dipendenti.id"), nullable=True)
    tipo_assenza: Mapped[str | None] = mapped_column(String, nullable=True)
    data_inizio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fine: Mapped[date | None] = mapped_column(Date, nullable=True)
    ora_inizio: Mapped[time | None] = mapped_column(Time, nullable=True)
    ora_fine: Mapped[time | None] = mapped_column(Time, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    confermata_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)
    confermata_il: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Tabella + id del record vero creato alla conferma (per tracciabilità:
    # da qui si arriva all'Assenza o alla Sostituzione effettiva).
    record_creato_tabella: Mapped[str | None] = mapped_column(String, nullable=True)
    record_creato_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    dipendente: Mapped[Dipendente | None] = relationship(foreign_keys=[dipendente_id])
    dipendente_sostituto: Mapped[Dipendente | None] = relationship(foreign_keys=[dipendente_sostituto_id])


class InvioGiornaliero(Base):
    """Traccia gli invii del riepilogo "chi è nei presidi domani" alla Camera
    dei Deputati (vedi app/riepilogo_giornaliero.py): una riga per
    data_riepilogo evita di rimandarlo due volte per errore lo stesso giorno
    (es. un riavvio del server proprio a cavallo dell'orario configurato)."""
    __tablename__ = "invii_riepilogo_giornaliero"
    __table_args__ = (
        UniqueConstraint("data_riepilogo", name="uq_invii_riepilogo_data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_riepilogo: Mapped[date] = mapped_column(Date, nullable=False)
    inviato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    destinatari: Mapped[str] = mapped_column(Text, nullable=False)
    manuale: Mapped[bool] = mapped_column(default=False, nullable=False)
    inviato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)


class AllarmeCoperturaInviato(Base):
    """Traccia gli invii del preavviso interno "un palazzo sarà sotto il
    minimo domani" ai gestori (vedi app/allarme_copertura.py): diverso dal
    riepilogo alla Camera dei Deputati (InvioGiornaliero sopra), serve a dare
    ancora tempo per trovare una sostituzione prima del suo orario di invio.
    Una riga per data_riferimento evita di ripetere l'allarme più volte lo
    stesso giorno."""
    __tablename__ = "allarmi_copertura_inviati"
    __table_args__ = (
        UniqueConstraint("data_riferimento", name="uq_allarmi_copertura_data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_riferimento: Mapped[date] = mapped_column(Date, nullable=False)
    inviato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    destinatari: Mapped[str] = mapped_column(Text, nullable=False)
    palazzi_carenti: Mapped[str] = mapped_column(Text, nullable=False)
    manuale: Mapped[bool] = mapped_column(default=False, nullable=False)
    inviato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)


class ImpostazioneImap(Base):
    """Configurazione della casella IMAP da cui leggere le email dei
    dipendenti (assenze/sostituzioni, vedi app/email_ingest.py),
    modificabile dall'amministratore dalla pagina /bozze-email senza dover
    editare app/email_config_locale.py a mano sul PC server. Una sola riga
    (id=1, vedi app/impostazioni_email.py): se manca o i campi sono vuoti,
    si ricade sui valori statici di app/email_config.py come prima."""
    __tablename__ = "impostazioni_imap"

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String, default="", nullable=False)
    porta: Mapped[int] = mapped_column(default=993, nullable=False)
    utente: Mapped[str] = mapped_column(String, default="", nullable=False)
    password: Mapped[str] = mapped_column(String, default="", nullable=False)
    cartella: Mapped[str] = mapped_column(String, default="INBOX", nullable=False)
    aggiornato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    aggiornato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)


class ImpostazioneAllarmeCopertura(Base):
    """Destinatari dell'allarme interno di carenza copertura (vedi
    app/allarme_copertura.py), modificabili SOLO dall'amministratore dalla
    pagina /allarme-copertura senza dover editare app/email_config_locale.py
    a mano. Una sola riga (id=1, vedi app/impostazioni_allarme_copertura.py):
    se manca o tutti e tre i campi sono vuoti, si ricade sulla lista statica
    ALLARME_COPERTURA_DESTINATARI di app/email_config.py come prima. Tre
    campi fissi invece di una lista libera perché così richiesto (fino a 3
    destinatari), non un limite tecnico del modello sottostante."""
    __tablename__ = "impostazioni_allarme_copertura"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_1: Mapped[str | None] = mapped_column(String, nullable=True)
    email_2: Mapped[str | None] = mapped_column(String, nullable=True)
    email_3: Mapped[str | None] = mapped_column(String, nullable=True)
    aggiornato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    aggiornato_da: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)


class LogModifica(Base):
    __tablename__ = "log_modifiche"
    __table_args__ = (
        CheckConstraint(f"azione IN {AZIONI_VALIDE}", name="ck_log_azione"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utente_id: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"), nullable=True)
    tabella: Mapped[str] = mapped_column(String, nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    azione: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    dettaglio: Mapped[str | None] = mapped_column(Text, nullable=True)

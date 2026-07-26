"""Configurazione posta elettronica per le notifiche automatiche (assenze e
sostituzioni registrate). Compila i valori qui sotto con quelli del tuo
provider di posta: funziona con qualunque provider SMTP standard (Aruba,
Gmail, Outlook/Office365, ecc.), non solo Aruba.

Come trovare questi dati: di solito sono indicati nelle impostazioni email
del tuo provider alla voce "server SMTP in uscita" / "outgoing mail server".
Esempi tipici:
  Aruba:             smtp.aruba.it, porta 465 (SSL) o 587 (STARTTLS)
  Gmail:             smtp.gmail.com, porta 587 (STARTTLS) — serve una
                      "password per le app", non la password normale
  Outlook/Office365: smtp.office365.com, porta 587 (STARTTLS)

Finché SMTP_HOST, SMTP_UTENTE, SMTP_PASSWORD e DESTINATARI_NOTIFICHE non
sono tutti compilati, le notifiche restano disattivate automaticamente: il
programma continua a funzionare normalmente, semplicemente non manda email.

NON aggiungere mai la vera password a un commit/repository condiviso: se il
progetto viene messo sotto controllo versione, tieni questo file fuori
(vedi .gitignore) oppure sostituiscilo con una copia da compilare a mano su
ogni PC server.
"""

# Server SMTP del tuo provider (vedi esempi sopra). Vuoto = notifiche spente.
SMTP_HOST = ""

# Porta SMTP: 465 se SMTP_USA_SSL è True, 587 (o 25) se è False (STARTTLS).
SMTP_PORTA = 587

# Se True, la connessione è cifrata fin dall'inizio (porta tipica 465).
# Se False, si usa STARTTLS su una connessione inizialmente in chiaro (587/25).
SMTP_USA_SSL = False

# Credenziali della casella di posta che invia le notifiche.
SMTP_UTENTE = ""
SMTP_PASSWORD = ""

# Indirizzo mostrato come mittente (di solito uguale a SMTP_UTENTE).
SMTP_MITTENTE = ""

# Uno o più indirizzi che ricevono le notifiche di assenze e sostituzioni.
DESTINATARI_NOTIFICHE: list[str] = []

# Secondi massimi di attesa per la connessione al server SMTP: evita che il
# programma resti bloccato a lungo se il server di posta non risponde.
SMTP_TIMEOUT_SECONDI = 10

# Stessa protezione per la lettura della posta in arrivo, dove serve anche di
# più: il polling gira in un thread di sfondo, e senza timeout un server che
# accetta la connessione ma poi non risponde (provider in difficoltà, firewall
# che inghiotte i pacchetti) lo lascia bloccato a tempo indeterminato. Non
# solleva nessuna eccezione, quindi il try/except attorno al ciclo non scatta:
# la lettura automatica delle richieste dei dipendenti smette di funzionare in
# silenzio, fino al riavvio del programma — che su quel PC può essere fra
# settimane. Più generoso di quello SMTP perché scaricare i messaggi è più
# lento che spedirne uno.
IMAP_TIMEOUT_SECONDI = 30


def notifiche_configurate() -> bool:
    """True solo se tutti i dati necessari per inviare sono stati compilati."""
    return bool(SMTP_HOST and SMTP_UTENTE and SMTP_PASSWORD and DESTINATARI_NOTIFICHE)


def smtp_configurato() -> bool:
    """True se il server SMTP è pronto per un invio a un destinatario scelto
    al momento (a differenza di notifiche_configurate(), che richiede anche
    una lista statica di destinatari fissa): usata per l'invio dei moduli
    assenze/sostituzioni ai singoli dipendenti da /bozze-email, dove il
    destinatario è l'indirizzo del dipendente scelto, non una lista fissa."""
    return bool(SMTP_HOST and SMTP_UTENTE and SMTP_PASSWORD)


# --- Lettura automatica delle email di assenza/sostituzione (IMAP) ---
# Vedi docs/06-formato-email-dipendenti.md per il formato che i dipendenti
# devono usare per scrivere a questa casella. Le email vengono lette e
# trasformate in bozze da confermare a mano (mai inserite da sole sul
# calendario): vedi /bozze-email nell'app.
#
# Questi valori si possono anche compilare/cambiare direttamente dalla
# pagina /bozze-email (sezione "Casella email per le richieste dei
# dipendenti", solo amministratore): se compilati da lì hanno la precedenza
# su quelli scritti qui sotto (vedi app/impostazioni_email.py). I valori
# qui restano utili come impostazione iniziale o come alternativa per chi
# preferisce editare un file invece di usare l'interfaccia.
#
# Come trovare questi dati: di solito sono indicati nelle impostazioni email
# del tuo provider alla voce "server IMAP in entrata" / "incoming mail server".
# Esempi tipici:
#   Aruba:  imaps.aruba.it, porta 993 (SSL)
#   Libero: imapmail.libero.it, porta 993 (SSL)
#   Gmail:  imap.gmail.com, porta 993 (SSL) — serve una "password per le app"
#
# Finché IMAP_HOST, IMAP_UTENTE e IMAP_PASSWORD non sono tutti compilati, la
# lettura automatica resta disattivata: il programma continua a funzionare
# normalmente, semplicemente non controlla la posta.

IMAP_HOST = ""
IMAP_PORTA = 993
IMAP_UTENTE = ""
IMAP_PASSWORD = ""

# Cartella da controllare (di solito la posta in arrivo, non cambiarla se
# non sai cosa significa).
IMAP_CARTELLA = "INBOX"

# Ogni quanti minuti controllare automaticamente la posta.
IMAP_INTERVALLO_MINUTI = 5


def imap_configurato() -> bool:
    """True solo se i dati necessari per collegarsi alla casella sono stati
    compilati."""
    return bool(IMAP_HOST and IMAP_UTENTE and IMAP_PASSWORD)


# --- Riepilogo giornaliero automatico (chi è nei presidi il giorno dopo) ---
# Sostituisce l'invio manuale che oggi fa una persona ogni giorno prima delle
# 20:00: usa lo stesso server SMTP configurato sopra, invia solo a
# RIEPILOGO_GIORNALIERO_DESTINATARI (non agli stessi indirizzi di
# DESTINATARI_NOTIFICHE, a meno che tu non li scriva anche qui).

# Metti True per attivare l'invio automatico (resta comunque disponibile il
# pulsante "Invia ora" manuale da /riepilogo-giornaliero indipendentemente
# da questo interruttore).
RIEPILOGO_GIORNALIERO_ABILITATO = False

# Indirizzo/i del referente Camera dei Deputati (e di chiunque altro debba
# ricevere il riepilogo).
RIEPILOGO_GIORNALIERO_DESTINATARI: list[str] = []

# Entro quest'ora (formato HH:MM, 24 ore) il riepilogo di domani deve essere
# partito: il programma lo controlla ogni pochi minuti e lo invia alla prima
# occasione dopo quest'orario, se non è già stato mandato oggi.
RIEPILOGO_GIORNALIERO_ORA = "19:00"


def riepilogo_giornaliero_configurato() -> bool:
    """True solo se SMTP e i destinatari del riepilogo sono stati compilati
    (indipendentemente dall'interruttore RIEPILOGO_GIORNALIERO_ABILITATO, che
    riguarda solo l'invio automatico, non il pulsante manuale)."""
    return bool(SMTP_HOST and SMTP_UTENTE and SMTP_PASSWORD and RIEPILOGO_GIORNALIERO_DESTINATARI)


# --- Allarme interno di carenza copertura ---
# Diverso dal riepilogo giornaliero sopra (quello va al referente Camera dei
# Deputati): questo avvisa i gestori se domani un palazzo risulterà sotto la
# copertura minima configurata (vedi /sedi e /sale), abbastanza in anticipo
# da poter ancora trovare una sostituzione prima delle 20:00.

# Metti True per attivare il controllo automatico (resta comunque disponibile
# il pulsante "Controlla ora" manuale da /allarme-copertura).
ALLARME_COPERTURA_ABILITATO = False

# Indirizzo/i dei gestori da avvisare (non necessariamente gli stessi di
# RIEPILOGO_GIORNALIERO_DESTINATARI: quello va al referente esterno, questo
# resta interno).
ALLARME_COPERTURA_DESTINATARI: list[str] = []

# Entro quest'ora (formato HH:MM, 24 ore) il controllo scatta per la prima
# volta: prima di questa non manda nulla, anche se già configurato. Va tenuta
# prima di RIEPILOGO_GIORNALIERO_ORA per lasciare tempo di reagire.
ALLARME_COPERTURA_ORA = "17:00"


def allarme_copertura_configurato() -> bool:
    """True solo se SMTP e i destinatari dell'allarme sono stati compilati
    (indipendentemente dall'interruttore ALLARME_COPERTURA_ABILITATO, che
    riguarda solo il controllo automatico, non il pulsante manuale)."""
    return bool(SMTP_HOST and SMTP_UTENTE and SMTP_PASSWORD and ALLARME_COPERTURA_DESTINATARI)


# Le vere credenziali vanno scritte in app/email_config_locale.py (un file
# escluso da git, vedi .gitignore), non qui sopra: così restano solo sul PC
# server e non finiscono mai in un commit. Copia
# app/email_config_locale.py.esempio per iniziare.
try:
    from app.email_config_locale import *  # noqa: F401,F403
except ImportError:
    pass

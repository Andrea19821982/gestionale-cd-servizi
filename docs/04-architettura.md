# Architettura tecnica

## Scelta dello stack
Python è già il linguaggio usato per gli altri strumenti Excel di CD Servizi, quindi è la scelta più sostenibile da mantenere nel tempo, anche con competenze IT non aggiornate quotidianamente.

- Backend: FastAPI, con SQLAlchemy per l'accesso al database SQLite.
- Frontend: Jinja2 per il rendering delle pagine, HTMX per le interazioni senza ricaricare la pagina intera, per esempio il salvataggio di una cella del calendario. Evitare framework JavaScript pesanti, tipo React o Vue, non necessari per questo caso d'uso e più difficili da mantenere per chi non lavora quotidianamente con essi.
- Generazione PDF: WeasyPrint, a partire dallo stesso template HTML usato per la vista a schermo.
- Autenticazione: sessione via cookie, password con hash bcrypt, tramite la libreria passlib.

## Perché non Electron
Electron aggiunge un intero runtime Chromium a ogni installazione, pesa centinaia di megabyte, e introduce un secondo linguaggio, JavaScript lato client complesso, oltre al Python del backend. Per un programma interno con poche decine di utenti, questo costo di manutenzione non è giustificato.

## Distribuzione in rete locale
Il programma gira in modalità client-server.

Un PC, quello di Andrea o un altro PC sempre acceso in ufficio, esegue il server: `CalendarioTurni-Server.exe`, un eseguibile PyInstaller che avvia FastAPI in ascolto sulla rete locale, per esempio sulla porta 8420, e ospita il file del database SQLite.

Ogni collega esegue `CalendarioTurni.exe`, un eseguibile leggero basato su pywebview, che apre una finestra simile a un programma nativo, puntata all'indirizzo del server. Al primo avvio, chiede l'indirizzo IP del server e lo salva in un file di configurazione locale.

Questa architettura evita di installare un vero server aziendale dedicato, e resta comunque centralizzata: tutti vedono sempre gli stessi dati aggiornati.

## Limite noto
SQLite gestisce bene le letture concorrenti, meno bene le scritture concorrenti frequenti. Per un ufficio di poche persone che modificano il calendario turni in momenti diversi della giornata, non è un problema pratico. Se in futuro il numero di utenti concorrenti in scrittura crescesse molto, valutare la migrazione a PostgreSQL, che FastAPI e SQLAlchemy supportano senza riscrivere la logica applicativa.

## Sicurezza
- Password mai salvate in chiaro.
- Ogni azione che modifica dati resta tracciata in `log_modifiche`, con utente e timestamp.
- Il ruolo consultazione è a sola lettura, senza accesso alle funzioni di modifica, nemmeno lato interfaccia.

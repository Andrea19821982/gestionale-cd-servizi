# Istruzioni per Claude Code — progetto calendario turni CD Servizi

## Obiettivo
Costruire un gestionale desktop per Windows che sostituisca il file Excel `Calendario_Mensile_.xlsm`, oggi usato per pianificare i turni del personale di pulizia e portierato nelle sedi della Camera dei Deputati. Il programma deve essere multiutente, usato da più colleghi sulla stessa rete locale, con login e permessi differenziati.

## Regole vincolanti
1. Stack tecnico: Python 3.11+, FastAPI, SQLite, SQLAlchemy, Jinja2 più HTMX per il frontend. Non introdurre altri framework, per esempio Electron o Node, senza autorizzazione esplicita di Andrea.
2. Target: Windows. L'eseguibile finale va pacchettizzato con PyInstaller.
3. Architettura client-server su rete locale, come descritto in `docs/04-architettura.md`.
4. Non inserire mai dati reali dei dipendenti nel codice, nei test o nei commit. Usare sempre dati fittizi generati appositamente, i nomi veri restano solo nel file Excel originale di Andrea.
5. Ogni modifica a turni, assenze o sostituzioni resta tracciata, con utente e data/ora, nella tabella `log_modifiche`.
6. Prima di scrivere codice, leggere tutti i file in `docs/`, in particolare `05-riferimento-excel.md`, che descrive la logica dell'attuale foglio Excel.
7. Procedere per fasi, come indicato in `docs/02-requisiti.md`, senza passare alla fase successiva finché la precedente non è testata e funzionante.

## Cosa chiedere ad Andrea se qualcosa non è chiaro
- Nomi e colori esatti delle sedi.
- Tipi di turno effettivamente in uso, oltre ai tre trovati nel file: 07:00-13:30, 13:30-20:00, 14:30-21:00.
- Tipologie di assenza da gestire, per esempio ferie, malattia, permesso.
- Come vengono oggi colorate le celle di sostituzione nel file Excel, a mano o con uno strumento, vedi la sezione "cosa non è stato verificato" in `docs/05-riferimento-excel.md`.

## Struttura della documentazione
- `docs/01-brief.md` — contesto e obiettivo del progetto
- `docs/02-requisiti.md` — requisiti funzionali, divisi per fasi
- `docs/03-modello-dati.md` — schema del database
- `docs/04-architettura.md` — scelte tecniche e distribuzione
- `docs/05-riferimento-excel.md` — analisi del file Excel di partenza

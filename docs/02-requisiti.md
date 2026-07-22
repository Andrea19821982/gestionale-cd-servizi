# Requisiti funzionali, per fasi

## Fase 1 — fondamenta
- Modello dati e database SQLite, vedi `03-modello-dati.md`.
- Autenticazione utenti con tre ruoli: amministratore, gestore turni, consultazione.
- Gestione anagrafica di sedi, dipendenti, tipi di turno.

## Fase 2 — vista calendario, sola lettura
- Vista mensile per sede, identica nella struttura al foglio Excel: righe per dipendenti, colonne per i giorni del mese.
- Selezione mese e anno, con ricalcolo automatico dei giorni del mese e riconoscimento dei weekend.
- Colonne weekend evidenziate graficamente, come nel file originale.

## Fase 3 — pianificazione turni
- Pattern di turno per dipendente: turno settimana dispari, turno settimana pari, usati per generare automaticamente la proposta di calendario del mese.
- Modifica manuale della singola cella, un dipendente in un giorno, con override del pattern automatico.
- Tracciamento dell'origine di ogni assegnazione: da pattern, manuale, o da sostituzione.

## Fase 4 — assenze
- Registrazione assenza: dipendente, data inizio, data fine, tipo, note.
- L'assenza copre automaticamente le celle del calendario nel periodo indicato, disattivando il turno.
- Elenco assenze filtrabile per dipendente e per periodo, equivalente al foglio REGISTRO ASSENZE del file attuale.

## Fase 5 — sostituzioni
- Registrazione sostituzione: chi parte, sede di partenza, chi sostituisce, sede di arrivo, note.
- Aggiornamento automatico della vista calendario della sede coinvolta, con il nominativo del sostituto.
- Colorazione della cella in base alla sede di provenienza del sostituto, come nella legenda del file attuale.
- Elenco sostituzioni, equivalente al foglio SOSTITUZIONI del file attuale.

## Fase 6 — stampa ed esportazione
- Esportazione PDF del calendario mensile, per singola sede o per tutte le sedi.
- Layout leggibile per stampa e affissione in bacheca.

## Fase 7 — distribuzione
- Pacchettizzazione del server con PyInstaller, avvio e arresto da system tray.
- Pacchettizzazione del client con pywebview, punta all'indirizzo del server.
- Configurazione dell'indirizzo server al primo avvio del client.

## Backlog, fuori dall'MVP
- Notifiche email automatiche per assenze o sostituzioni registrate, riutilizzando l'integrazione SMTP Aruba già usata in altri progetti di Andrea.
- Esportazione anche in formato Excel, per chi ancora lo richiede.
- Statistiche ore lavorate e ferie residue.
- Integrazione futura con il software RSPP a cui Andrea sta lavorando separatamente.

# Analisi del file Excel di partenza — Calendario_Mensile_.xlsm

Questo documento descrive quello che è stato trovato nel file caricato da Andrea. Serve come riferimento per non perdere logiche già in uso.

## Fogli presenti
- MONTECITORIO, VALDINA, EX BANCO DI NAPOLI, SEMINARIO, THEODOLI: un foglio per sede, stessa struttura.
- REGISTRO ASSENZE: colonne Inizio Assenza, Fine Assenza, Nominativo, Tipo Assenza, Note.
- SOSTITUZIONI: colonne Data, Persona che cambia, Palazzo di destinazione, Persona che sostituisce, Palazzo di destinazione, Note.
- _nomi: foglio di appoggio, nascosto, con nominativo, sede di appartenenza, numero di riga nel foglio della sede. Serve probabilmente per liste a discesa o formule di ricerca.

## Struttura di ogni foglio-sede
- Riga di intestazione con i numeri dei giorni del mese, 1-31, e l'iniziale del giorno della settimana.
- Colonna A: nominativo del dipendente.
- Colonne B-AF: turno del giorno corrispondente, in formato testo, per esempio "07:00 - 13:30".
- Celle AI1 e AI2: mese, 1-12, e anno, usate per ricalcolare la vista.
- Due colonne finali, "Turno sett. dispari" e "Turno sett. pari": pattern di base del dipendente, probabilmente usato per compilare manualmente il resto della griglia mese per mese.
- Una colonna con note testuali per riga, tra cui "Legenda – colore = palazzo di destinazione", "Sostituzione → nome sede", "Weekend, nessun turno".

## Macro VBA presente
Un solo macro attivo, nell'evento Workbook_SheetChange: quando cambia il valore di mese o anno nelle celle AI1:AI2 di un foglio-sede, ricalcola l'ultimo giorno del mese e restringe la larghezza delle colonne che cadono di sabato o domenica. È l'unica automazione presente nel file: tutto il resto, inserimento turni, assenze, sostituzioni, è manuale.

## Cosa non è stato verificato con certezza
Il file usa formattazione condizionale e convalida dati con estensioni recenti di Excel, che gli strumenti di lettura automatica non interpretano del tutto. Non è quindi certo se:
- La colorazione delle celle per le sostituzioni sia automatica, tramite formattazione condizionale, oppure manuale.
- Esistano menu a tendina per la scelta del turno o del nominativo.

Prima di replicare pixel per pixel questi dettagli, conviene chiedere direttamente ad Andrea come vengono compilate oggi le celle colorate, se a mano o con uno strumento.

## Tre fasce orarie trovate nei dati
- 07:00 - 13:30
- 13:30 - 20:00
- 14:30 - 21:00

Vanno trattate come dati configurabili, in tabella `tipi_turno`, non come valori fissi nel codice, perché potrebbero cambiare o aumentare.

## Nota sui dati reali
Il file caricato contiene nominativi reali di personale della Camera dei Deputati. Questi dati non vanno mai copiati nel repository di codice, nei test, o nei commit. Per lo sviluppo e i test, usare sempre nominativi e sedi fittizi.

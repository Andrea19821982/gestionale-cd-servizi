# Contesto e obiettivo

Andrea lavora per CD Servizi S.p.A., ufficio tecnico, e oggi pianifica i turni del personale con un file Excel, `Calendario_Mensile_.xlsm`. Il file gestisce cinque sedi della Camera dei Deputati: Montecitorio, Valdina, ex Banco di Napoli, Seminario, Theodoli. Ogni sede ha un foglio con l'elenco del personale e la griglia dei turni giornalieri del mese.

Il file funziona, ma ha i limiti tipici di un Excel condiviso: nessun controllo su chi modifica cosa, nessuno storico delle modifiche, rischio di sovrascritture quando più persone lo aprono insieme, nessuna vista d'insieme su tutte le sedi.

L'obiettivo è costruire un programma dedicato, con la stessa logica operativa del file Excel, ma con un'interfaccia più simile a un gestionale: login, permessi differenziati, moduli separati per turni, assenze, sostituzioni. Il riferimento a Zucchetti, fatto da Andrea, va inteso come ispirazione nello spirito dell'interfaccia, gestionale web pulito, non come impegno a replicarne le funzioni specifiche, che restano in gran parte sconosciute a questo livello di dettaglio.

Ricostruire l'intera piattaforma Zucchetti non è realistico né utile: copre paghe, presenze, HR, con anni di sviluppo di un intero team. Questo progetto si limita a replicare, e migliorare, quello che il file Excel già fa oggi.

## Utenti e contesto d'uso
- Uso in ufficio, più colleghi collegati alla stessa rete locale.
- Eseguibile Windows, nessuna competenza di installazione richiesta ai colleghi.
- Ruoli diversi: chi amministra il sistema, chi pianifica i turni, chi consulta soltanto.

## Cosa non è questo progetto
- Non è un software di rilevazione presenze con badge o timbrature.
- Non è un software paghe.
- Non sostituisce il registro presenze ufficiale della Camera dei Deputati, resta uno strumento operativo interno di CD Servizi.

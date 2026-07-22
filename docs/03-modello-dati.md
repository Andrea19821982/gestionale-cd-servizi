# Modello dati

## sedi
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| nome | testo | es "Montecitorio" |
| colore_hex | testo | colore identificativo, usato per le sostituzioni |
| attivo | booleano | |

## dipendenti
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| cognome | testo | |
| nome | testo | |
| sede_riferimento_id | riferimento a sedi | sede di appartenenza abituale |
| ordine_visualizzazione | intero | per mantenere l'ordine del foglio Excel |
| attivo | booleano | |

## tipi_turno
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| etichetta | testo | es "Mattina" |
| ora_inizio | orario | es 07:00 |
| ora_fine | orario | es 13:30 |

Nel file attuale sono presenti tre fasce orarie: 07:00-13:30, 13:30-20:00, 14:30-21:00. Vanno inserite come dati configurabili in questa tabella, non come valori fissi nel codice, perché possono cambiare.

## pattern_turno
| campo | tipo | note |
|---|---|---|
| dipendente_id | riferimento a dipendenti | |
| turno_settimana_dispari_id | riferimento a tipi_turno | |
| turno_settimana_pari_id | riferimento a tipi_turno | |

## assegnazioni_giornaliere
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| dipendente_id | riferimento a dipendenti | |
| data | data | |
| sede_effettiva_id | riferimento a sedi | può differire dalla sede di riferimento, in caso di sostituzione |
| tipo_turno_id | riferimento a tipi_turno, nullable | nullo se assente |
| origine | testo | uno tra pattern, manuale, sostituzione, assenza |
| note | testo | |

## assenze
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| dipendente_id | riferimento a dipendenti | |
| data_inizio | data | |
| data_fine | data | |
| tipo_assenza | testo | es ferie, malattia, permesso, da confermare con Andrea |
| note | testo | |
| creato_da | riferimento a utenti | |
| creato_il | data e ora | |

## sostituzioni
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| data | data | |
| dipendente_partente_id | riferimento a dipendenti | |
| sede_partenza_id | riferimento a sedi | |
| dipendente_sostituto_id | riferimento a dipendenti | |
| sede_arrivo_id | riferimento a sedi | |
| note | testo | |
| creato_da | riferimento a utenti | |
| creato_il | data e ora | |

## utenti
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| username | testo, univoco | |
| password_hash | testo | mai salvare la password in chiaro |
| ruolo | testo | amministratore, gestore_turni, consultazione |
| dipendente_collegato_id | riferimento a dipendenti, nullable | utile se un dipendente deve vedere solo il proprio turno |
| attivo | booleano | |

## log_modifiche
| campo | tipo | note |
|---|---|---|
| id | intero, chiave primaria | |
| utente_id | riferimento a utenti | |
| tabella | testo | |
| record_id | intero | |
| azione | testo | creazione, modifica, cancellazione |
| timestamp | data e ora | |
| dettaglio | testo | valori prima e dopo, in formato leggibile |

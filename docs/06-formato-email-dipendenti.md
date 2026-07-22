# Formato email per assenze e sostituzioni

Da distribuire ai dipendenti (stampato o via messaggio) per l'indirizzo email
dedicato a cui scrivere per segnalare un'assenza o una sostituzione. Il
programma legge automaticamente queste email e prepara la richiesta pronta
da confermare — **non serve altro che scrivere l'email in questo formato**.

Indirizzo a cui scrivere: **da compilare con l'indirizzo reale scelto**
(es. `turni@cdservizi.it`).

⚠️ Importante: la richiesta non è effettiva finché un amministrativo non la
conferma da programma. Se l'assenza è urgente, avvisare comunque anche
telefonicamente.

---

## 1. Per segnalare un'assenza (ferie, malattia, permesso)

**Oggetto dell'email:** `ASSENZA`

**Corpo dell'email**, una riga per ogni campo, esattamente in questo formato
`Etichetta: valore`:

```
Nome: Mario Rossi
Tipo: Ferie
Dal: 10/08/2026
Al: 12/08/2026
Note: 
```

- **Nome**: cognome e nome esattamente come noti in azienda.
- **Tipo**: Ferie, Malattia o Permesso (o altra dicitura breve).
- **Dal / Al**: data di inizio e fine assenza, formato `gg/mm/aaaa`. Per un
  solo giorno, ripetere la stessa data in entrambi i campi.
- **Note**: facoltativo, si può lasciare vuoto.

### Esempio compilato

```
Oggetto: ASSENZA

Nome: Mario Rossi
Tipo: Ferie
Dal: 10/08/2026
Al: 14/08/2026
Note: rientro il 15
```

---

## 2. Per segnalare una sostituzione

**Oggetto dell'email:** `SOSTITUZIONE`

**Corpo dell'email:**

```
Data: 10/08/2026
Assente: Mario Rossi
Sostituto: Luca Verdi
Orario: intera giornata
```

- **Data**: giorno della sostituzione, formato `gg/mm/aaaa`.
- **Assente**: chi normalmente lavorerebbe quel giorno.
- **Sostituto**: chi lo sostituisce.
- **Orario**: scrivere `intera giornata`, oppure l'orario esatto se la
  sostituzione copre solo una parte del turno, es. `09:00-13:00`.

### Esempio compilato

```
Oggetto: SOSTITUZIONE

Data: 10/08/2026
Assente: Mario Rossi
Sostituto: Luca Verdi
Orario: intera giornata
```

---

## Regole generali

- Un'email = una sola assenza o una sola sostituzione. Per segnalare più
  cose, mandare più email separate.
- L'oggetto deve contenere la parola `ASSENZA` o `SOSTITUZIONE` (anche
  insieme ad altro testo, es. "ASSENZA - Mario Rossi" va bene).
- Ogni campo va su una riga separata, con i due punti `:` dopo l'etichetta.
- Il nome va scritto per intero (cognome e nome), non solo il nome di
  battesimo: se in azienda ci sono più persone con lo stesso nome, il
  programma non riesce a capire di chi si tratta e la richiesta resta
  segnalata come da controllare a mano.
- Se qualcosa non è chiaro (data scritta in modo diverso, nome non trovato),
  il programma non inventa: segna la richiesta come "da controllare" e la
  mostra così com'è a chi la deve confermare.

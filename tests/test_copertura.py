from datetime import date, time, timedelta

from app.models import AssegnazioneGiornaliera, Dipendente, EventoSala, Sala, Sede, SottosezioneCopertura, TipoTurno
from app.routers.copertura import calcola_copertura
from tests.conftest import login


def _crea_sede(db, nome="Sede Test"):
    sede = Sede(nome=nome, colore_hex="#123456", attivo=True)
    db.add(sede)
    db.commit()
    db.refresh(sede)
    return sede


def _login_admin(client, crea_utente):
    crea_utente("admin_test", "passwordsegreta", "amministratore")
    login(client, "admin_test", "passwordsegreta")


def test_copertura_distingue_presente_assente_non_pianificato(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db)
    tipo = TipoTurno(etichetta="Mattina Cop", ora_inizio=time(7, 0), ora_fine=time(13, 30))
    db.add(tipo)
    db.commit()
    db.refresh(tipo)

    presente = Dipendente(cognome="Presente", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    assente = Dipendente(cognome="Assente", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    non_pianificato = Dipendente(cognome="NonPianificato", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([presente, assente, non_pianificato])
    db.commit()
    for d in (presente, assente, non_pianificato):
        db.refresh(d)

    oggi = date(2026, 8, 10)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=presente.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.add(AssegnazioneGiornaliera(
        dipendente_id=assente.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=None, origine="assenza",
    ))
    db.commit()

    r = client.get(f"/copertura?data={oggi.isoformat()}")
    assert r.status_code == 200
    testo = r.text
    riga_presente = testo.split("Presente Test")[1].split("</tr>")[0]
    riga_assente = testo.split("Assente Test")[1].split("</tr>")[0]
    riga_non_pianificato = testo.split("NonPianificato Test")[1].split("</tr>")[0]
    assert "Presente</span>" in riga_presente
    assert "Assente</span>" in riga_assente
    assert "Non pianificato</span>" in riga_non_pianificato
    assert "1 presenti su 3" in testo


def test_copertura_richiede_login(client):
    r = client.get("/copertura", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_copertura_accessibile_a_consultazione(client, crea_utente):
    crea_utente("consultazione_test", "passwordsegreta", "consultazione")
    login(client, "consultazione_test", "passwordsegreta")
    r = client.get("/copertura")
    assert r.status_code == 200


def test_copertura_minima_zero_senza_configurazione(db):
    _crea_sede(db)
    oggi = date.today()
    blocchi = calcola_copertura(db, oggi)
    assert blocchi[0]["copertura_minima"] == 0
    assert blocchi[0]["sotto_minimo"] is False


def test_copertura_minima_segnala_carenza_su_ciascuna_fascia(db):
    sede = _crea_sede(db)
    sede.copertura_minima_mattina = 2
    sede.copertura_minima_pomeriggio = 1
    db.commit()
    oggi = date.today()
    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["copertura_minima_mattina"] == 2
    assert blocco["copertura_minima_pomeriggio"] == 1
    assert blocco["presenti"] == 0
    assert blocco["sotto_minimo_mattina"] is True
    assert blocco["sotto_minimo_pomeriggio"] is True
    assert blocco["sotto_minimo"] is True


def test_evento_in_sala_aumenta_copertura_minima_di_entrambe_le_fasce(db):
    sede = _crea_sede(db)
    sede.copertura_minima_mattina = 1
    sede.copertura_minima_pomeriggio = 1
    db.commit()
    sala = Sala(nome="Sala della Lupa Test", sede_id=sede.id, copertura_minima_aggiuntiva=3, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    oggi = date.today()
    db.add(EventoSala(sala_id=sala.id, data_inizio=oggi, data_fine=oggi, descrizione="Seduta"))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["copertura_minima_mattina"] == 4  # 1 ordinaria + 3 per l'evento
    assert blocco["copertura_minima_pomeriggio"] == 4
    assert len(blocco["eventi_oggi"]) == 1
    assert blocco["eventi_oggi"][0].sala_id == sala.id
    assert blocco["sotto_minimo"] is True


def test_evento_fuori_data_non_conta(db):
    sede = _crea_sede(db)
    sede.copertura_minima_mattina = 1
    db.commit()
    sala = Sala(nome="Sala Fuori Data", sede_id=sede.id, copertura_minima_aggiuntiva=5, attivo=True)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    oggi = date.today()
    db.add(EventoSala(sala_id=sala.id, data_inizio=oggi + timedelta(days=5), data_fine=oggi + timedelta(days=6)))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    assert blocchi[0]["copertura_minima_mattina"] == 1
    assert blocchi[0]["eventi_oggi"] == []


def test_sala_disattivata_non_conta_anche_con_evento_attivo(db):
    sede = _crea_sede(db)
    sede.copertura_minima_mattina = 1
    db.commit()
    sala = Sala(nome="Sala Disattivata", sede_id=sede.id, copertura_minima_aggiuntiva=5, attivo=False)
    db.add(sala)
    db.commit()
    db.refresh(sala)
    oggi = date.today()
    db.add(EventoSala(sala_id=sala.id, data_inizio=oggi, data_fine=oggi))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    assert blocchi[0]["copertura_minima_mattina"] == 1
    assert blocchi[0]["eventi_oggi"] == []


def test_presenti_sufficienti_non_segnalano_carenza(db):
    sede = _crea_sede(db)
    sede.copertura_minima_mattina = 1
    db.commit()
    tipo = TipoTurno(etichetta="Mattina Copertura Test", ora_inizio=time(7, 0), ora_fine=time(13, 30), fascia="mattina")
    db.add(tipo)
    dip = Dipendente(cognome="Bianchi", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.refresh(tipo)
    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["presenti"] == 1
    assert blocco["presenti_mattina"] == 1
    assert blocco["copertura_minima_mattina"] == 1
    assert blocco["sotto_minimo"] is False


def test_turno_senza_fascia_classificata_non_conta_per_nessun_minimo(db):
    """TipoTurno.fascia è None finché l'amministratore non lo classifica in
    Tipi turno: chi lo ha assegnato compare comunque come "presente"
    nell'elenco, ma non concorre al minimo di nessuna delle due fasce."""
    sede = _crea_sede(db)
    sede.copertura_minima_mattina = 1
    db.commit()
    tipo = TipoTurno(etichetta="Non Classificato", ora_inizio=time(9, 0), ora_fine=time(13, 0), fascia=None)
    db.add(tipo)
    dip = Dipendente(cognome="Bianchi", nome="NonClassificato", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.refresh(tipo)
    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["presenti"] == 1
    assert blocco["presenti_mattina"] == 0
    assert blocco["sotto_minimo_mattina"] is True
    # Il conteggio di quanti presenti restano fuori solo per questo motivo
    # deve essere esposto: senza saperlo, l'avviso "sotto il minimo" sembra
    # sbagliato a chi guarda (le persone ci sono, il turno non è ancora
    # classificato) — vedi l'avviso mostrato in copertura.html.
    assert blocco["presenti_non_classificati"] == 1


def test_pagina_copertura_avvisa_se_turno_non_classificato_influenza_il_minimo(client, crea_utente, db):
    """Senza questo avviso, un minimo mattina/pomeriggio configurato ma con
    i turni reali ancora tutti non classificati risulta sempre "sotto il
    minimo" anche a organico pieno, senza che sia chiaro perché: l'avviso
    deve comparire quando la carenza può dipendere da questo."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Avviso Fascia")
    sede.copertura_minima_mattina = 1
    tipo = TipoTurno(etichetta="Non Classificato Avviso", ora_inizio=time(9, 0), ora_fine=time(13, 0), fascia=None)
    db.add(tipo)
    dip = Dipendente(cognome="Avviso", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.refresh(tipo)
    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    r = client.get(f"/copertura?data={oggi.isoformat()}")
    assert r.status_code == 200
    assert "non ancora classificato" in r.text
    assert "/tipi-turno" in r.text


def test_pagina_copertura_non_avvisa_se_tutti_i_turni_sono_classificati(client, crea_utente, db):
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Senza Avviso")
    sede.copertura_minima_mattina = 1
    tipo = TipoTurno(etichetta="Classificato Avviso", ora_inizio=time(9, 0), ora_fine=time(13, 0), fascia="mattina")
    db.add(tipo)
    dip = Dipendente(cognome="SenzaAvviso", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.refresh(tipo)
    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    r = client.get(f"/copertura?data={oggi.isoformat()}")
    assert r.status_code == 200
    assert "non ancora classificato" not in r.text


def test_suggerisce_dipendenti_non_pianificati_in_altre_sedi(db):
    sede_carente = _crea_sede(db, nome="Sede Carente")
    sede_carente.copertura_minima_mattina = 2
    sede_altra = _crea_sede(db, nome="Sede Altra")
    db.commit()

    libero_altrove = Dipendente(cognome="Libero", nome="Altrove", sede_riferimento_id=sede_altra.id, attivo=True)
    libero_qui = Dipendente(cognome="Libero", nome="Qui", sede_riferimento_id=sede_carente.id, attivo=True)
    db.add_all([libero_altrove, libero_qui])
    db.commit()

    oggi = date.today()
    blocchi = calcola_copertura(db, oggi)
    blocco_carente = next(b for b in blocchi if b["sede"].id == sede_carente.id)
    blocco_altro = next(b for b in blocchi if b["sede"].id == sede_altra.id)

    assert blocco_carente["sotto_minimo"] is True
    suggeriti_id = {dip.id for dip in blocco_carente["dipendenti_suggeriti"]}
    assert libero_altrove.id in suggeriti_id
    # Un dipendente non pianificato nella STESSA sede carente non è un
    # suggerimento utile (non è una risorsa "libera altrove").
    assert libero_qui.id not in suggeriti_id
    # Un blocco che rispetta il minimo non propone suggerimenti.
    assert blocco_altro["dipendenti_suggeriti"] == []


def test_sottosezione_ha_blocco_e_minimo_separati_dalla_sede_principale(db):
    """Un comparto come "Parcheggio" dentro Valdina (Dipendente.sottosezione
    + SottosezioneCopertura) va monitorato con un proprio minimo, non
    mischiato con quello della sede: un dipendente del comparto non entra
    nel conteggio "presenti" del blocco principale della sede, e viceversa."""
    sede = _crea_sede(db, nome="Valdina Test")
    sede.copertura_minima_mattina = 5
    db.add(SottosezioneCopertura(sede_id=sede.id, nome="Parcheggio", copertura_minima_mattina=1))
    db.commit()

    tipo = TipoTurno(etichetta="Mattina Parcheggio", ora_inizio=time(7, 0), ora_fine=time(13, 30), fascia="mattina")
    db.add(tipo)
    dip_principale = Dipendente(cognome="Principale", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    dip_parcheggio = Dipendente(
        cognome="Parcheggiato", nome="Test", sede_riferimento_id=sede.id, attivo=True, sottosezione="Parcheggio",
    )
    db.add_all([dip_principale, dip_parcheggio])
    db.commit()
    db.refresh(tipo)
    db.refresh(dip_parcheggio)

    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip_parcheggio.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocchi_sede = [b for b in blocchi if b["sede"].id == sede.id]
    assert len(blocchi_sede) == 2

    blocco_principale = next(b for b in blocchi_sede if b["nome_sottosezione"] is None)
    blocco_parcheggio = next(b for b in blocchi_sede if b["nome_sottosezione"] == "Parcheggio")

    assert blocco_principale["totale"] == 1
    assert blocco_principale["presenti"] == 0
    assert blocco_principale["sotto_minimo_mattina"] is True  # 0 presenti su 5 richiesti

    assert blocco_parcheggio["totale"] == 1
    assert blocco_parcheggio["presenti"] == 1
    assert blocco_parcheggio["copertura_minima_mattina"] == 1
    assert blocco_parcheggio["sotto_minimo_mattina"] is False
    assert blocco_parcheggio["nome_visualizzato"] == "Valdina Test — Parcheggio"


def test_calcola_copertura_rispetta_ordine_visualizzazione(db):
    """Le sedi compaiono nell'ordine impostato in Sedi (ordine_visualizzazione),
    non semplicemente in ordine alfabetico: a parità di numero, alfabetico
    come prima (vedi Zeta con ordine 0, in fondo nonostante il nome)."""
    zeta = Sede(nome="Zeta", colore_hex="#111111", attivo=True, ordine_visualizzazione=0)
    alfa = Sede(nome="Alfa", colore_hex="#222222", attivo=True, ordine_visualizzazione=5)
    beta = Sede(nome="Beta", colore_hex="#333333", attivo=True, ordine_visualizzazione=-1)
    db.add_all([zeta, alfa, beta])
    db.commit()

    blocchi = calcola_copertura(db, date.today())
    nomi_in_ordine = [b["sede"].nome for b in blocchi]
    assert nomi_in_ordine == ["Beta", "Zeta", "Alfa"]


def test_riga_assente_ha_il_pulsante_organizza_sostituzione(client, crea_utente, db):
    """Il pulsante deve comparire solo su chi è ASSENTE, non su chi è
    presente o non pianificato: una sostituzione sostituisce qualcuno, un
    "non pianificato" è un turno da assegnare, non un buco da coprire."""
    _login_admin(client, crea_utente)
    sede = _crea_sede(db, "Sede Pulsante")
    presente = Dipendente(cognome="PresenteBtn", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    assente = Dipendente(cognome="AssenteBtn", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    non_pian = Dipendente(cognome="NonPianBtn", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add_all([presente, assente, non_pian])
    db.commit()
    for d in (presente, assente, non_pian):
        db.refresh(d)

    tipo = TipoTurno(etichetta="Mattina Btn", ora_inizio=time(7, 0), ora_fine=time(13, 30))
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    oggi = date(2026, 8, 12)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=presente.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=tipo.id, origine="manuale",
    ))
    db.add(AssegnazioneGiornaliera(
        dipendente_id=assente.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=None, origine="assenza",
    ))
    db.commit()

    r = client.get(f"/copertura?data={oggi.isoformat()}")
    testo = r.text

    link_atteso = (
        f"/sostituzioni?precompila_partente_id={assente.id}"
        f"&precompila_sede_id={sede.id}&precompila_data={oggi.isoformat()}#nuova-sostituzione"
    )
    assert link_atteso in testo
    # Non deve comparire un secondo pulsante agganciato a chi non è assente:
    # cerca l'href specifico per gli id degli altri due, che non deve esistere.
    assert f"precompila_partente_id={presente.id}&" not in testo
    assert f"precompila_partente_id={non_pian.id}&" not in testo


def test_consultazione_non_vede_il_pulsante_organizza_sostituzione(client, crea_utente, db):
    """Chi è di sola consultazione non può creare sostituzioni: il pulsante
    non deve nemmeno comparire, oltre a non funzionare se forzato via URL."""
    crea_utente("admin_cop", "passwordsegreta", "amministratore")
    login(client, "admin_cop", "passwordsegreta")
    sede = _crea_sede(db, "Sede Consultazione")
    assente = Dipendente(cognome="AssenteCons", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(assente)
    db.commit()
    db.refresh(assente)
    oggi = date(2026, 8, 13)
    db.add(AssegnazioneGiornaliera(
        dipendente_id=assente.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=None, origine="assenza",
    ))
    db.commit()

    crea_utente("sola_lettura_cop", "passwordsegreta", "consultazione")
    login(client, "sola_lettura_cop", "passwordsegreta")

    r = client.get(f"/copertura?data={oggi.isoformat()}")
    assert "Organizza sostituzione" not in r.text


def test_turno_entrambe_conta_sia_per_mattina_sia_per_pomeriggio(db):
    """Un turno intermedio (es. 11:00-17:30) copre parte di entrambe le
    fasce. Prima esisteva solo mattina/pomeriggio/non-classificato, e
    "non-classificato" significava "non conta mai": un comparto coperto
    con un turno atipico su una sola fascia sarebbe risultato sempre sotto
    il minimo di entrambe, a organico pieno, senza alcun avviso che lo
    spiegasse (l'avviso "non classificato" esiste solo per l'assenza di
    classificazione, non per questo caso)."""
    sede = _crea_sede(db, "Sede Entrambe")
    sede.copertura_minima_mattina = 1
    sede.copertura_minima_pomeriggio = 1
    db.commit()
    intermedio = TipoTurno(etichetta="Intermedio", ora_inizio=time(11, 0), ora_fine=time(17, 30), fascia="entrambe")
    db.add(intermedio)
    dip = Dipendente(cognome="Intermedio", nome="Test", sede_riferimento_id=sede.id, attivo=True)
    db.add(dip)
    db.commit()
    db.refresh(dip)
    db.refresh(intermedio)
    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip.id, data=oggi, sede_effettiva_id=sede.id, tipo_turno_id=intermedio.id, origine="manuale",
    ))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocco = blocchi[0]
    assert blocco["presenti_mattina"] == 1
    assert blocco["presenti_pomeriggio"] == 1
    assert blocco["presenti_non_classificati"] == 0
    assert blocco["sotto_minimo_mattina"] is False
    assert blocco["sotto_minimo_pomeriggio"] is False


def test_mattina_e_pomeriggio_con_orari_diversi_per_palazzi_diversi(client, crea_utente, db):
    """Il conteggio di copertura dipende solo da TipoTurno.fascia, non
    dagli orari effettivi: si possono avere tipi "Mattina"/"Pomeriggio"
    diversi per nome e orario in ogni palazzo, e ciascuno conta comunque
    per il minimo del proprio palazzo, indipendentemente da come si
    chiamano o dagli orari degli altri."""
    sede_a = _crea_sede(db, "Palazzo Uno")
    sede_b = _crea_sede(db, "Palazzo Due")
    sede_a.copertura_minima_mattina = 1
    sede_b.copertura_minima_mattina = 1
    db.commit()

    mattina_a = TipoTurno(etichetta="Mattina Palazzo Uno", ora_inizio=time(7, 0), ora_fine=time(13, 30), fascia="mattina")
    mattina_b = TipoTurno(etichetta="Mattina Palazzo Due", ora_inizio=time(8, 30), ora_fine=time(15, 0), fascia="mattina")
    db.add_all([mattina_a, mattina_b])
    dip_a = Dipendente(cognome="PalazzoUno", nome="Test", sede_riferimento_id=sede_a.id, attivo=True)
    dip_b = Dipendente(cognome="PalazzoDue", nome="Test", sede_riferimento_id=sede_b.id, attivo=True)
    db.add_all([dip_a, dip_b])
    db.commit()
    for x in (mattina_a, mattina_b, dip_a, dip_b):
        db.refresh(x)

    oggi = date.today()
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip_a.id, data=oggi, sede_effettiva_id=sede_a.id, tipo_turno_id=mattina_a.id, origine="manuale",
    ))
    db.add(AssegnazioneGiornaliera(
        dipendente_id=dip_b.id, data=oggi, sede_effettiva_id=sede_b.id, tipo_turno_id=mattina_b.id, origine="manuale",
    ))
    db.commit()

    blocchi = calcola_copertura(db, oggi)
    blocco_a = next(b for b in blocchi if b["sede"].id == sede_a.id)
    blocco_b = next(b for b in blocchi if b["sede"].id == sede_b.id)
    assert blocco_a["presenti_mattina"] == 1 and blocco_a["sotto_minimo_mattina"] is False
    assert blocco_b["presenti_mattina"] == 1 and blocco_b["sotto_minimo_mattina"] is False

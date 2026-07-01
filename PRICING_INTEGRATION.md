# Valutazione integrazione automatica dei listini (medio termine)

Obiettivo: sostituire (o affiancare) lo scraping quotidiano di `TARIFFE_TASK.md`
con una fonte strutturata di tariffe pay-per-use, mantenendo invariato lo schema
di `content/tariffe.json` che il front-end già consuma.

## Stato attuale

- `content/tariffe.json`: archivio curato, aggiornato dalla routine di
  `TARIFFE_TASK.md` via WebFetch/WebSearch sui siti ufficiali dei CPO.
- La pagina mostra inoltre il campo `UsageCost` di OpenChargeMap per singola
  stazione (testo libero, qualità variabile): già attivo, costo zero.

## Opzione A — Chargeprice API

**Cosa offre.** Database europeo di tariffe CPO/EMP con API JSON:

- `GET /v1/tariffs`: elenco tariffe con provider e canone mensile.
- `POST /v1/tariff_details`: prezzi unitari (€/kWh, fee a sessione, a minuto)
  per una tariffa su un CPO o una stazione specifica.
- Documentazione: <https://chargeprice.github.io/chargeprice-api-docs/>

**Licenza.** Chiave demo gratuita (dati limitati, **uso commerciale vietato**);
licenza commerciale via `sales@chargeprice.net`. Anche se TNT News è un blog
sperimentale, la pubblicazione dei dati sul sito va chiarita con loro prima di
andare in produzione: la demo va usata solo per la valutazione interna.

**Piano di valutazione (PoC).**

1. Richiedere la chiave demo dal form nella documentazione.
2. Script una tantum che, per ogni `gestore` di `tariffe.json`, cerca il CPO
   corrispondente su Chargeprice (per nome/alias) e scarica i prezzi ad-hoc.
3. Criteri di successo:
   - copertura ≥ 80% dei 19 gestori in archivio (in particolare Enel X Way,
     Plenitude/Be Charge, A2A, Free To X, Ewiva, Ionity, Tesla);
   - prezzi coerenti con i listini ufficiali a campione (±5%);
   - presenza della tariffa *ad-hoc/direct* distinta da quelle in abbonamento.
4. Se il PoC passa: chiedere condizioni di licenza e, se sostenibili,
   sostituire i passi 2–3 di `TARIFFE_TASK.md` con una chiamata API
   deterministica che riscrive i `prezzo` mantenendo `nome`, `alias`,
   `prefixes` e lo schema esistente. Lo scraping resta come fallback per i
   gestori non coperti.

## Opzione B — PUN (Piattaforma Unica Nazionale, MASE/GSE)

**Cosa offre.** Anagrafe istituzionale dei punti di ricarica italiani
(<https://www.piattaformaunicanazionale.it/>): posizione, potenza, CPO, stato.
Con il regolamento europeo AFIR i CPO devono esporre i prezzi ad-hoc; la PUN è
il canale naturale per l'Italia.

**Stato (metà 2026).** I dati sono dichiarati "esposti via API" ma l'accesso
non è self-service; l'export CSV pubblico ha problemi noti di formato
(cfr. <https://github.com/ondata/rete_ricarica_veicoli_elettrici>). I prezzi
in tempo reale dipendono dall'interoperabilità con i CPO, in completamento.

**Piano di valutazione.**

1. Richiedere al GSE l'accesso API per riuso dei dati (citare finalità
   informativa e AFIR art. 20).
2. Monitorare trimestralmente lo stato degli open data (repo onData sopra).
3. Quando i prezzi ad-hoc saranno esposti: la PUN diventa la fonte primaria
   per i CPO italiani (gratuita e ufficiale), con Chargeprice o scraping per
   gli operatori esteri (Ionity, Tesla, EnBW).

## Raccomandazione

1. **Subito:** PoC Chargeprice con chiave demo (mezza giornata di lavoro,
   nessun impegno economico) e richiesta di accesso API alla PUN in parallelo.
2. **Decisione:** se Chargeprice copre i gestori a costi sostenibili, adottarla
   come fonte primaria; altrimenti restare sullo scraping irrobustito
   (`listino_url` + log per gestore) in attesa della PUN.
3. **In ogni caso:** lo schema di `tariffe.json` resta l'interfaccia stabile
   verso il front-end; qualunque fonte scrive lì, così mappa e tabella
   comparativa non cambiano.

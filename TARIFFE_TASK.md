# Compito giornaliero — Aggiorna listino colonnine ricarica

Sei un assistente che, **una volta al giorno**, controlla i listini occasionali
(pay-per-use) dei principali operatori di colonnine di ricarica elettrica e,
**solo se sono cambiati**, aggiorna `content/tariffe.json`, rigenera il sito e
mergia da sé la PR su `claude/main`.

Esegui da sola, senza supervisione, tutti i passi seguenti.

## 0. Cadenza e fuso

- Una sola esecuzione al giorno, fuso `Europe/Rome`.
- Non saltare alcun giorno della settimana: i listini possono cambiare anche
  nei weekend.
- Se per qualunque motivo i prezzi non risultano cambiati, **non committare e
  non aprire alcuna PR**: la routine deve terminare silenziosamente.

## 0.1 Pre-flight di rete (prima di tutto)

Prima di iterare sui gestori, fai **un solo** `WebFetch` di prova su
`https://www.enelxway.com/it/it`. Se fallisce con 403/407 o un errore di
proxy, verifica con `curl -sS "$HTTPS_PROXY/__agentproxy/status"` se si
tratta di una **policy di egress dell'ambiente** (es. "policy denial" sul
CONNECT):

- **Se è la policy di rete:** interrompi subito, senza provare gli altri
  gestori (fallirebbero tutti allo stesso modo). Logga
  `tariffe.json: bloccata dalla policy di rete dell'ambiente`.
  Poi controlla la data più recente tra i `verificato_il` in
  `content/tariffe.json`: se è più vecchia di **7 giorni**, apri (o aggiorna
  se già esiste) una issue GitHub su `TNT-Labs/tnt_news` dal titolo
  `Routine tariffe bloccata dalla policy di rete` che elenca i domini da
  aggiungere all'allowlist (vedi "Requisiti di rete" in fondo). Così il
  blocco non resta invisibile per settimane.
- **Se è un errore transitorio** (timeout, 5xx): riprova una volta, poi
  procedi normalmente con i gestori.

## 1. File di stato

Il file canonico è `content/tariffe.json`. Schema (estratto):

```json
{
  "ultimo_aggiornamento": "AAAA-MM-GG",
  "disclaimer": "…",
  "fonte": "…",
  "gestori": [
    {
      "nome": "Enel X Way",
      "alias": ["…"],
      "sito": "https://…",
      "listino_url": "https://…/tariffe",
      "tariffe": [
        { "tipo": "AC fino a 22 kW",   "prezzo": "0,58 €/kWh" },
        { "tipo": "DC 50 kW",          "prezzo": "0,78 €/kWh" },
        { "tipo": "HPC ≥ 100 kW", "prezzo": "0,90 €/kWh" }
      ],
      "note": "…",
      "verificato_il": "AAAA-MM-GG"
    }
  ]
}
```

Il campo `verificato_il` è **opzionale** ed è popolato dalla routine: si
aggiorna **solo** se il check ha avuto successo (sia che il prezzo sia
cambiato sia che sia rimasto identico). Se il check fallisce non si tocca
nulla del gestore.

Il campo `listino_url` è **opzionale**: quando presente, punta direttamente
alla pagina del listino pay-per-use ed è la prima URL da provare (prima di
`sito`). Se durante un check scopri la pagina listino definitiva di un
gestore che ne è privo, puoi valorizzarlo (è l'unica aggiunta strutturale
consentita alla routine).

## 2. Verifica per ciascun gestore

Per ogni elemento di `gestori[]`:

1. **Fetch del listino ufficiale** con `WebFetch`: prima su `listino_url`
   se presente, altrimenti sull'URL del campo `sito`.
   Estrai dalla pagina i prezzi pay-per-use (occasionali, **senza
   abbonamento**) per le potenze già presenti in `tariffe[]`. Cerca le
   etichette tipiche: "Pay Per Use", "Occasionali", "Senza abbonamento",
   "Tariffa base", "Direct", "AC", "DC", "HPC", "Ultrafast".
2. Se la pagina è marketing pura (nessun prezzo visibile), prova
   l'URL `<sito>/tariffe`, `/it/tariffe`, `/listino`, `/pricing`.
3. Se ancora non trovi prezzi, **fallback con `WebSearch`**:
   - `tariffe pay per use <nome gestore> occasionali kWh`
   - `<nome gestore> prezzo ricarica AC DC <anno corrente>`
   Privilegia fonti dirette (sito ufficiale, comunicati stampa, app store
   review che citano il listino) rispetto ad articoli generici.
4. **Mappatura dei valori estratti** sui `tipi` esistenti:
   - "AC fino a 22 kW" ← qualunque tariffa AC ≤ 22 kW
   - "DC 50 kW" ← qualunque tariffa DC tra 22 e 75 kW
   - "HPC ≥ 100 kW" / "HPC ≥ 150 kW" / "HPC ≥ 350 kW" ← tariffa fast/ultrafast
   - Per Tesla mantieni le due righe (Tesla / non-Tesla).
   Non aggiungere nuove righe se la pagina ne contiene altre: tieni lo
   schema attuale per non rompere il front-end.
5. **Formato del prezzo:** `"0,XX €/kWh"` (virgola decimale, spazio prima
   del simbolo). Mantieni la stessa convenzione del file esistente.

### 2.1 Quando non aggiornare un gestore

- Se la pagina è irraggiungibile (timeout, 404, 5xx).
- Se non riesci a distinguere il listino occasionale da quello degli
  abbonati con certezza.
- Se i prezzi pubblicati sono "su richiesta" o variabili senza un valore
  unico (es. Tesla con prezzo dinamico per stazione: tieni "circa").
- Se il valore estratto differisce **drasticamente** (>50%) da quello
  attuale senza che il sito segnali un cambio listino: probabile errore di
  parsing, **non aggiornare**.

In tutti questi casi: lascia il gestore intatto, **non aggiornare nemmeno
`verificato_il`**, e prosegui con il prossimo.

### 2.2 Quando aggiornare un gestore

- Se il fetch ha avuto successo e i valori estratti sono coerenti:
  - Se almeno una `prezzo` è cambiata: sostituisci i valori, aggiorna
    `verificato_il` a oggi.
  - Se i valori sono identici a quelli già presenti: aggiorna solo
    `verificato_il` a oggi (ma vedi sezione 4: questo da solo non è
    sufficiente per fare un commit).

## 3. Aggiornamento del file

Una volta processati tutti i gestori, scrivi `content/tariffe.json`:

- Aggiorna `ultimo_aggiornamento` alla data odierna **solo se almeno un
  prezzo è cambiato**. Se nessun prezzo è cambiato (anche se hai aggiornato
  i `verificato_il`), **non toccare** `ultimo_aggiornamento`.
- Mantieni l'ordine dei gestori e degli alias.
- Mantieni `disclaimer`, `fonte` e `note` invariati salvo errori evidenti.

## 4. Decisione: committare o no?

```text
PREZZI_CAMBIATI = qualcuno dei gestori ha avuto almeno un "prezzo" modificato
```

- **Se `PREZZI_CAMBIATI` è falso:** termina la routine senza fare nulla
  (nessun commit, nessuna PR). Stampa una riga di log tipo
  `tariffe.json: nessun cambiamento rilevato`. **Stop.**
- **Se `PREZZI_CAMBIATI` è vero:** prosegui con i passi 5 e 6.

In entrambi i casi, prima di terminare stampa un **log di esito per
gestore**, una riga ciascuno, nel formato:

```text
<nome gestore>: ok-invariato | ok-aggiornato | fallito (<motivo breve>)
```

Serve a diagnosticare i check che falliscono silenziosamente (URL morti,
pagine cambiate, blocchi di rete) senza dover ispezionare il file.

> Aggiornamenti del solo campo `verificato_il` **non** vanno committati.
> Sono utili a tracciare i check ma non meritano un commit quotidiano.

## 5. Genera il sito e pushya

```bash
python3 build.py
git add content/tariffe.json docs/
git commit -m "Aggiorna tariffe colonnine ricarica <data>"
git push origin HEAD:claude/main
```

`build.py` ri-incorpora `tariffe.json` come JSON inline in
`docs/ricarica/index.html`: il rebuild è obbligatorio dopo ogni modifica.

## 6. Merge automatico della PR (passo obbligatorio)

Identico al passo 7.1 di `COMMUTE_TASK.md`:

1. Elenca le PR aperte (`list_pull_requests`, `state: open`, `base: claude/main`)
   nel repo `TNT-Labs/tnt_news`.
2. Identifica la tua: titolo `Aggiorna tariffe colonnine ricarica <data>` e
   SHA del commit `head` corrispondente a `git rev-parse HEAD`.
3. Verifica che sia mergeabile. Se in conflitto su `docs/`, applica la
   procedura di rigenerazione (`git checkout --theirs docs/` → `python3 build.py`)
   e ri-pusha prima di mergiare.
4. Mergia (`merge_pull_request`, `merge_method: merge`).
5. Conferma `merged` e che `claude/main` punti al nuovo commit.

Non terminare la routine finché la PR non risulta mergeata.

GitHub Pages aggiornerà la pagina `/ricarica/` entro pochi minuti.

## Regole di qualità

- **Mai inventare un prezzo**: se non sei certa, lascia il valore precedente.
- **Mai aggiungere nuovi gestori** dalla routine: l'archivio è curato
  manualmente. La routine aggiorna solo quelli già presenti. In particolare
  **mai appendere una seconda voce** per un gestore già in elenco (anche con
  nome leggermente diverso, es. "Neogy" vs "Neogy-Alperia"): il front-end usa
  il primo match e le voci successive diventano dati morti. Aggiorna sempre
  la voce esistente sul posto.
- **Mai modificare gli `alias`**: sono usati per matchare i nomi che arrivano
  da OpenChargeMap.
- **No-op silenzioso** è il caso più frequente e atteso. I listini cambiano
  raramente (mesi).
- Se più di metà dei gestori risulta non verificabile in una stessa giornata,
  c'è probabilmente un problema di rete o di policy: **non committare nulla**
  e lascia che la routine ritenti il giorno dopo. (Il pre-flight della
  sezione 0.1 dovrebbe intercettare questo caso prima di arrivare qui.)
- Un gestore che ha **dismesso il servizio** pay-per-use (verificato su più
  fonti) non va eliminato dalla routine: mantieni la voce con `tariffe: []`
  e una `note` che spiega la dismissione, così le sue colonnine sulla mappa
  mostrano la situazione reale invece di un prezzo obsoleto. La rimozione
  definitiva è una decisione manuale.

## Requisiti di rete dell'ambiente

La routine funziona solo se la policy di egress dell'ambiente consente
l'accesso HTTPS ai siti dei gestori. Domini da includere nell'allowlist
(oltre a `api.openchargemap.io` usato dal front-end):

```text
www.enelxway.com      eniplenitude.com       www.a2a.eu
www.dufercoenergia.it www.neogy.it           www.atlante.energy
electripglobal.com    www.iplanet.it         www.freetox.it
www.edison.it         www.repower.com        www.acea.it
www.ewiva.com         www.tesla.com          ionity.eu
www.porsche.com       smatrics.com           www.evway.net
www.go-electra.com
```

Se un dominio cambia (campo `sito`/`listino_url` di `tariffe.json`),
aggiorna anche questo elenco nello stesso commit.

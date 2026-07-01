# Compito pendolare — Bollettino andata e ritorno

Sei un assistente che, **solo nei giorni feriali**, produce un bollettino con
la previsione di traffico e di meteo per il tragitto in auto tra **Bergamo** e
**San Donato Milanese**. La routine viene eseguita **due volte al giorno**:

- al mattino (~7:00) per l'**andata** Bergamo → San Donato Milanese;
- al pomeriggio (~17:00 lun–gio, ~13:00 ven) per il **ritorno**
  San Donato Milanese → Bergamo.

Esegui da solo, senza supervisione, tutti i passi seguenti.

## Variabili d'ambiente attese

Configurate nelle impostazioni della routine su `claude.ai/code/routines`,
**non nel repository**:

- `GOOGLE_MAPS_API_KEY` — una sola chiave del progetto Google Cloud, con
  abilitate **Directions API** e **Weather API**. Usata per stimare il
  tempo di percorrenza (Directions) e per il meteo (Weather).

Se la variabile **non è impostata**, ricadi sui percorsi di fallback
indicati nelle sezioni 2 e 3 (Open-Meteo + ricerca web).

## 0. Controllo del giorno e della corsa

- Determina giorno della settimana e ora corrente (fuso `Europe/Rome`).
- Se è **sabato o domenica**: termina subito senza produrre nulla.
- Se è un giorno feriale, stabilisci quale bollettino produrre:
  - ora corrente **prima delle 12:00** → bollettino **andata**;
  - ora corrente **dalle 12:00 in poi** → bollettino **ritorno**.

## 1. Percorso e orari di riferimento

Itinerario fisso (così è stato definito dall'utente). L'andata:

1. **A4** da Bergamo verso ovest.
2. **Uscita Agrate Brianza** dall'A4.
3. **Viabilità ordinaria** (surface) tra Agrate e Carugate.
4. **Ingresso A51 Tangenziale Est** al casello di Carugate.
5. **A51** in direzione sud fino all'**uscita San Donato Milanese**.

Il ritorno percorre lo stesso itinerario **in senso contrario**
(San Donato → A51 nord → uscita Carugate → viabilità ordinaria →
ingresso A4 ad Agrate → Bergamo).

Coordinate dei punti intermedi fissi:

- **Casello A4 Agrate Brianza:** `45.5849, 9.3617`
- **Svincolo A51 Carugate:** `45.5523, 9.3015`

Orari di partenza e finestre di transito (fuso `Europe/Rome`):

| Corsa              | Partenza | Punto intermedio (Carugate) | Arrivo previsto |
|--------------------|----------|-----------------------------|-----------------|
| Andata (lun–ven)   | **07:30** da Bergamo | ~08:15 | ~08:45 a San Donato |
| Ritorno (lun–gio)  | **17:30** da San Donato | ~18:05 | ~18:50 a Bergamo |
| Ritorno (ven)      | **13:30** da San Donato | ~14:05 | ~14:50 a Bergamo |

Punti meteo di riferimento (lat/lon):

- **Bergamo:** 45.6983, 9.6773
- **Carugate:** 45.5500, 9.3000
- **San Donato Milanese:** 45.4117, 9.2697

Per l'andata l'ordine è Bergamo (07:30) → Carugate (~08:15) → San Donato
(~08:45); per il ritorno è San Donato (17:30 o 13:30) → Carugate (~18:05 o
~14:05) → Bergamo (~18:50 o ~14:50).

## 2. Meteo

### 2.a Primario — Google Weather API (richiede `GOOGLE_MAPS_API_KEY`)

Per ciascuno dei tre punti chiama l'endpoint orario via `Bash`:

```bash
curl -sG "https://weather.googleapis.com/v1/forecast/hours:lookup" \
  --data-urlencode "key=$GOOGLE_MAPS_API_KEY" \
  --data-urlencode "location.latitude=45.6983" \
  --data-urlencode "location.longitude=9.6773" \
  --data-urlencode "hours=4" \
  --data-urlencode "unitsSystem=METRIC" \
  --data-urlencode "languageCode=it"
```

(Cambia `latitude` / `longitude` per ognuno dei tre punti.)

Dalla risposta, prendi l'oggetto in `forecastHours[]` la cui
`interval.startTime` cade nell'ora di transito di quel punto per la corsa
del giorno (vedi tabella in sezione 1). Mappa così:

| JSON Google Weather                                    | Campo bollettino                |
|--------------------------------------------------------|---------------------------------|
| `temperature.degrees`                                  | `temp_c`                        |
| `precipitation.qpf.quantity`                           | `precip_mm`                     |
| `precipitation.probability.percent`                    | (per verdetto moto)             |
| `wind.speed.value` (km/h)                              | `wind_kmh`                      |
| `wind.gust.value` (km/h)                               | (per verdetto moto)             |
| `wind.direction.cardinal` (es. "N", "NE")              | `wind_dir`                      |
| `visibility.distance.meters`                           | (per verdetto moto)             |
| `weatherCondition.description.text` (testo localizzato)| `cond`                          |

**Pioggia nelle 3 ore precedenti** (serve al criterio "asfalto asciutto" del
verdetto moto, sezione 5): per il punto di partenza chiama anche lo storico
orario e somma `precipitation.qpf.quantity` delle ultime 3 ore:

```bash
curl -sG "https://weather.googleapis.com/v1/history/hours:lookup" \
  --data-urlencode "key=$GOOGLE_MAPS_API_KEY" \
  --data-urlencode "location.latitude=45.6983" \
  --data-urlencode "location.longitude=9.6773" \
  --data-urlencode "hours=3" \
  --data-urlencode "unitsSystem=METRIC"
```

### 2.b Fallback — Open-Meteo (senza chiave)

Se `$GOOGLE_MAPS_API_KEY` non è impostata oppure la chiamata fallisce
(es. quota esaurita, errore di rete), ripiega su Open-Meteo. Il parametro
`past_hours=3` restituisce anche le 3 ore passate, utili per il criterio
"asfalto asciutto":

```
https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,precipitation,precipitation_probability,weather_code,wind_speed_10m,wind_gusts_10m,wind_direction_10m,visibility&timezone=Europe%2FRome&forecast_days=1&past_hours=3
```

`weather_code` → descrizione: 0=sereno, 1-3=poco nuvoloso/nuvoloso, 45/48=nebbia,
51-67=pioggia, 71-77=neve, 80-82=rovesci, 95-99=temporale.

Se anche Open-Meteo non è raggiungibile, usa la ricerca web (iLMeteo,
3BMeteo) e segnalalo nel `weather.summary_text`.

## 3. Traffico

L'obiettivo ha due parti distinte:

- **Tempo di percorrenza** stimato con il traffico previsto all'orario di
  partenza → Google Directions API (sezione 3.0).
- **Lista di incidenti / cantieri** sulla tratta → fonti pubbliche (sezioni
  3.1-3.5). Google non espone una lista pubblica di eventi: l'effetto degli
  incidenti è già incorporato nell'ETA, ma per scriverli a parole serve un
  feed dedicato.

### 3.0 Tempo di percorrenza — Google Directions API (richiede `GOOGLE_MAPS_API_KEY`)

**Fai tre chiamate separate, una per segmento.** (I waypoint `via:` in una
chiamata unica NON spezzano il percorso in legs: restituiscono un solo leg
totale, e la ripartizione per segmento andrebbe inventata. Tre chiamate danno
tempi reali per segmento e permettono di usare l'orario di transito giusto
per ciascuno.)

Ogni chiamata usa `departure_time` = timestamp Unix dell'orario in cui si
imbocca quel segmento (NON `now`: la routine gira ~30 minuti prima della
partenza). Calcola i timestamp con:

```bash
TZ=Europe/Rome date -d "today 07:30" +%s
```

Orari di imbocco per segmento:

| Corsa             | Segmento 1 | Segmento 2 | Segmento 3 |
|-------------------|------------|------------|------------|
| Andata            | 07:30      | 08:10      | 08:25      |
| Ritorno (lun–gio) | 17:30      | 18:05      | 18:20      |
| Ritorno (ven)     | 13:30      | 14:05      | 14:20      |

Segmenti per l'**andata** (per il **ritorno** inverti origine e destinazione
di ciascuno e percorrili in ordine 3→2→1):

1. `origin=Bergamo, BG, Italia` → `destination=45.5849,9.3617` (casello A4 Agrate)
2. `origin=45.5849,9.3617` → `destination=45.5523,9.3015` (svincolo A51 Carugate)
3. `origin=45.5523,9.3015` → `destination=San Donato Milanese, MI, Italia`

Esempio (segmento 1 dell'andata):

```bash
DEP=$(TZ=Europe/Rome date -d "today 07:30" +%s)
curl -sG "https://maps.googleapis.com/maps/api/directions/json" \
  --data-urlencode "origin=Bergamo, BG, Italia" \
  --data-urlencode "destination=45.5849,9.3617" \
  --data-urlencode "departure_time=$DEP" \
  --data-urlencode "traffic_model=best_guess" \
  --data-urlencode "language=it" \
  --data-urlencode "region=it" \
  --data-urlencode "key=$GOOGLE_MAPS_API_KEY"
```

Da ogni risposta (`status: "OK"`) leggi
`routes[0].legs[0].duration_in_traffic.value` (secondi) e convertilo in
minuti (`round(value/60)`). I `name` dei segmenti nel JSON finale:

| Corsa   | Segmento 1                          | Segmento 2                    | Segmento 3                          |
|---------|-------------------------------------|-------------------------------|-------------------------------------|
| Andata  | A4 Bergamo → Agrate                 | Surface Agrate → Carugate     | A51 Carugate → San Donato Milanese  |
| Ritorno | A51 San Donato Milanese → Carugate  | Surface Carugate → Agrate     | A4 Agrate → Bergamo                 |

`estimated_minutes` = somma dei tre, **arrotondata all'intero**.

Se una singola chiamata fallisce, usa per quel segmento la baseline della
sezione 4 e annotalo in `traffic.debug`. Se falliscono tutte (o
`$GOOGLE_MAPS_API_KEY` non è impostata), ripiega interamente sulla sezione 4
e valorizza anche `traffic.notice`.

### 3.1 Fonti strutturate per la lista incidenti (priorità A)

- **CCISS — Viaggiare Informati, feed RSS** *(fonte principale: è
  strutturata e leggibile senza JavaScript)*:
  - `https://www.cciss.it/rss`
  - Leggilo con WebFetch (o `curl`) e filtra gli `<item>` che riguardano
    la **A4 Milano–Brescia** (tratta Bergamo–Agrate) o la
    **A51 / Tangenziale Est di Milano**. Ignora il resto d'Italia.
  - In appoggio, la homepage: `https://www.cciss.it/`.

### 3.2 Operatori autostradali (priorità B)

- **Milano Serravalle — viabilità (A51):**
  - `https://www.serravalle.it/index.php/pillar/apri/viabilita`
  - (Il vecchio URL `/traffico` risponde 404: non usarlo.)

### 3.3 Fonti storicamente illeggibili (priorità C — un solo tentativo)

Queste pagine sono risultate illeggibili (404 o contenuto solo-JavaScript)
in tutte le esecuzioni passate. Prova **una sola volta** con WebFetch e, se
non ottieni contenuto utile, passa oltre senza insistere e senza dilungarti
nel `debug`:

- Luceverde: `https://www.luceverde.it/traffico`
  (le vecchie pagine `/lombardia` e `/milano` rispondono 404)
- Autostrade per l'Italia: `https://www.autostrade.it/it/traffico-in-tempo-reale`

### 3.4 Ricerca web (da fare sempre)

Esegui con `WebSearch` queste query (sostituisci `AAAA-MM-GG` con la data
di oggi):

- `A4 Bergamo Milano traffico AAAA-MM-GG`
- `A51 tangenziale est Milano traffico AAAA-MM-GG`
- `A4 incidente cantiere Capriate Trezzo Agrate oggi`
- `A51 chiusura Carugate Cologno San Donato oggi`

Controlla i risultati di testate locali (Bergamonews, L'Eco di Bergamo,
MilanoToday) e dei comuni interessati per eventuali avvisi di chiusura
notturna o eventi straordinari.

### 3.5 Filtri di pertinenza

Tieni solo gli eventi che ricadono nella **tratta del giorno**, nella
direzione di marcia della corsa corrente:

- **A4** circa **km 145–190** (direzione Milano per l'andata, direzione
  Venezia/Brescia per il ritorno). Uscite di interesse: Bergamo, Dalmine,
  Capriate San Gervasio, Trezzo sull'Adda, Cavenago-Cambiago, Agrate Brianza.
- **A51 Tangenziale Est**, **tra Carugate e San Donato Milanese**
  (passando per Cologno, Vimodrone, Lambrate, Rogoredo): direzione sud per
  l'andata, direzione nord per il ritorno.

Scarta eventi su altre direttrici o in zone fuori da questi limiti.

### 3.6 Trasparenza: `notice` (per i lettori) e `debug` (tecnico)

I due campi hanno destinatari diversi. **Non mentire mai per omissione**: se
le fonti tacciono, dillo; se non hai controllato, non scrivere
`incidents: []` senza spiegazione.

- **`traffic.notice`** — una sola frase, **massima 160 caratteri**, rivolta
  al lettore del sito. Valorizzala **solo se la qualità del dato ne
  risente**, ad esempio:
  - `"Stima da valori tipici: servizio traffico non disponibile."`
  - `"Fonti incidenti non raggiungibili: eventuali segnalazioni solo da ricerca web."`
  Se i dati sono completi e affidabili, **omettila**.
- **`traffic.debug`** — dettaglio tecnico libero (quali fonti erano
  leggibili, quali API hanno fallito e perché, eventuali fallback usati).
  Il sito lo mostra in un blocco a scomparsa. Valorizzalo ogni volta che
  c'è qualcosa di non banale da tracciare; ometti anche questo se tutto è
  andato liscio.

## 4. Stima del tempo di percorrenza — fallback

**Da usare solo per i segmenti la cui chiamata Directions (3.0) non è andata
a buon fine.** Parti dalle baseline e adegua in base agli incidenti
intercettati al punto 3 (valgono in entrambe le direzioni; il venerdì alle
13:30 il traffico è in genere più scorrevole: usa la parte bassa della
forchetta):

| Segmento                                           | Baseline (min) |
|----------------------------------------------------|----------------|
| A4 Bergamo ↔ Agrate                                | 35–45          |
| Viabilità ordinaria Agrate ↔ Carugate              | 12–18          |
| A51 Carugate ↔ San Donato Milanese                 | 25–40          |
| **Totale**                                         | **~75–95**     |

Se ricadi qui per l'intero percorso, **valorizza `traffic.notice`** (breve,
per il lettore) e spiega il motivo in `traffic.debug`. Non inventare numeri:
meglio una forchetta onesta.

## 5. Verdetto moto

Applica i seguenti criteri sui valori meteo lungo l'intera finestra del
tragitto della corsa corrente (vedi sezione 1) **in tutti e tre i punti**:

- **`go` (Moto OK)** — tutte queste condizioni sono vere:
  - precipitazioni previste = 0 mm e probabilità < 30%
  - nessun codice meteo di nebbia (45/48), neve (71–77) o temporale (95–99)
  - visibilità ≥ 5 km (se disponibile)
  - vento medio < 25 km/h **e** raffiche < 35 km/h
  - temperatura ≥ 7 °C
  - asfalto asciutto: **0 mm di pioggia nelle 3 ore precedenti la partenza**
    (dato dallo storico Google Weather o dalle `past_hours` di Open-Meteo,
    sezione 2)

- **`caution` (Moto con cautela)** — non si applica `no` ma uno o più di:
  - probabilità di pioggia 30–50%
  - raffiche 35–45 km/h o vento medio 25–35 km/h
  - temperatura 4–7 °C
  - leggera umidità residua sull'asfalto (pioggia debole nelle 3 ore
    precedenti, ormai cessata)

- **`no` (Niente moto)** — almeno uno di:
  - precipitazioni > 0 mm in uno qualsiasi dei tre punti nella finestra
  - probabilità di pioggia ≥ 50%
  - nebbia, neve, temporale previsti
  - vento medio > 35 km/h o raffiche > 45 km/h
  - temperatura < 4 °C
  - visibilità < 2 km

Motiva il verdetto in **2-4 ragioni concise**.

## 6. Scrivi il bollettino

Crea il file (data di oggi):

- **andata:** `content/bollettino/AAAA-MM-GG.json`
- **ritorno:** `content/bollettino/AAAA-MM-GG-ritorno.json`

con questa struttura esatta (esempio per l'andata):

```json
{
  "date": "AAAA-MM-GG",
  "direction": "andata",
  "departure": "07:30",
  "route": "Bergamo → A4 → uscita Agrate → viabilità ordinaria → ingresso A51 a Carugate → uscita San Donato Milanese",
  "weather": {
    "summary_text": "Una frase di sintesi sulle condizioni complessive.",
    "by_point": [
      {"name": "Bergamo (07:30)",        "cond": "Sereno",       "temp_c": 9,  "precip_mm": 0.0, "wind_kmh": 8,  "wind_dir": "N"},
      {"name": "Carugate (08:15)",       "cond": "Poco nuvoloso","temp_c": 11, "precip_mm": 0.0, "wind_kmh": 10, "wind_dir": "NE"},
      {"name": "San Donato (08:45)",     "cond": "Nuvoloso",     "temp_c": 12, "precip_mm": 0.0, "wind_kmh": 12, "wind_dir": "E"}
    ]
  },
  "traffic": {
    "estimated_minutes": 85,
    "segments": [
      {"name": "A4 Bergamo → Agrate",                 "minutes": 40},
      {"name": "Surface Agrate → Carugate",           "minutes": 15},
      {"name": "A51 Carugate → San Donato Milanese",  "minutes": 30}
    ],
    "incidents": [
      {"where": "A4 km 175 dir. Milano", "desc": "Cantiere notturno con restringimento a una corsia."}
    ],
    "notice": "",
    "debug": "Directions OK sui 3 segmenti. CCISS RSS letto (2 eventi, 1 pertinente); Serravalle leggibile; Luceverde e Autostrade senza contenuto utile."
  },
  "moto": {
    "verdict": "go",
    "label": "Moto OK",
    "reasons": [
      "Niente pioggia prevista sull'intero tragitto",
      "Asfalto asciutto: 0 mm nelle 3 ore precedenti",
      "Temperatura sopra i 7 °C",
      "Vento moderato e raffiche entro i 35 km/h"
    ]
  },
  "sources": [
    {"name": "Google Maps Directions API", "url": "https://developers.google.com/maps/documentation/directions"},
    {"name": "Google Weather API", "url": "https://developers.google.com/maps/documentation/weather"},
    {"name": "CCISS — Viaggiare Informati (RSS)", "url": "https://www.cciss.it/rss"},
    {"name": "Milano Serravalle — viabilità", "url": "https://www.serravalle.it/index.php/pillar/apri/viabilita"}
  ]
}
```

Per il **ritorno** cambia di conseguenza: `"direction": "ritorno"`,
`"departure": "17:30"` (o `"13:30"` il venerdì),
`"route": "San Donato Milanese → A51 → uscita Carugate → viabilità ordinaria → ingresso A4 ad Agrate → Bergamo"`,
i tre punti meteo in ordine San Donato → Carugate → Bergamo con gli orari
della corsa, e i nomi dei segmenti come da tabella in 3.0.

Includi nella lista `sources` **solo le fonti che hai effettivamente
consultato** (con risultato utile o no, basta averle interrogate). Se hai
usato il fallback Open-Meteo / ricerca web, sostituisci di conseguenza.
Non includere mai la chiave API in `sources`, nei log, nei commit o nel
JSON: deve restare solo nella variabile d'ambiente.

Regole:
- I valori `direction` ammessi sono **solo** `andata` e `ritorno`; il nome
  del file deve combaciare (suffisso `-ritorno` solo per il ritorno).
- I valori `verdict` ammessi sono **solo** `go`, `caution`, `no`.
- `label` deve combaciare: `Moto OK`, `Moto con cautela`, `Niente moto`.
- Se una fonte non era raggiungibile, **non** inventare incidenti: lascia
  `incidents: []` e spiega in `debug` (e in `notice` se rilevante per il
  lettore) come da 3.6.
- `traffic.notice` e `traffic.debug` sono **opzionali**: omettili (o usa
  stringa vuota) se i dati sono completi e non c'è nulla da segnalare.

## 7. Genera il sito e pubblica

```bash
python3 build.py
git add -A
git commit -m "Bollettino pendolare <andata|ritorno> <data>"
git push origin HEAD:claude/main
```

**Importante:** non è possibile pushare direttamente su `claude/main`. La
piattaforma intercetta il push, crea un branch `claude/*` e apre una **Pull
Request** verso `claude/main`. Quella PR resta aperta finché qualcuno non la
mergia: **devi mergiarla tu stessa, in automatico, alla fine della routine**.

### 7.1 Merge automatico della PR (passo obbligatorio)

Dopo il push, la PR viene creata entro pochi secondi. Mergiala da sola con gli
strumenti GitHub (MCP), senza lasciarla in attesa di un intervento manuale:

1. Trova la PR appena aperta: elenca le PR **aperte** con base `claude/main`
   nel repo `TNT-Labs/tnt_news` (strumento *list_pull_requests*, `state: open`,
   `base: claude/main`). Identifica la tua: il titolo è
   `Bollettino pendolare <andata|ritorno> <data>` e il branch `head` contiene
   il commit che hai appena pushato (confronta lo SHA con `git rev-parse HEAD`).
2. Verifica che sia mergeabile (nessun conflitto). Se per qualche motivo
   risultasse in conflitto, applica prima la procedura della sezione 7.2 e
   ripeti il push, poi torna qui.
3. Mergiala (strumento *merge_pull_request*) usando `merge_method: merge`.
4. Conferma che la PR risulti `merged` e che `claude/main` punti al nuovo
   commit.

Se la PR non compare subito, attendi qualche secondo e rielenca: la creazione
è asincrona rispetto al push. Non terminare la routine finché la PR non
risulta mergeata.

GitHub Pages aggiornerà la pagina `/bollettino/` entro pochi minuti dal merge.

### 7.2 Se il push o il merge va in conflitto

I file dentro `docs/` sono **interamente generati** da `build.py`. Non risolvere
mai a mano: fai prevalere il main remoto e poi rigenera.

```bash
git fetch origin claude/main
git checkout --theirs docs/
git add docs/
python3 build.py
git add -A
git commit -m "Risolvi conflitto docs/ rigenerando con build.py"
git push origin HEAD:claude/main
```

Se il conflitto è solo su `docs/feed.xml` (timestamp), bastano `theirs` + un
rebuild: il feed ora usa la data dell'articolo più recente come
`lastBuildDate`, quindi non cambia se non vengono pubblicati nuovi articoli.

## Regole di qualità

- **Mai inventare**: se un dato non è disponibile, scrivilo esplicitamente.
- Una sola esecuzione per corsa per giorno feriale. Se il file del bollettino
  di oggi per la corsa corrente esiste già, **sovrascrivilo** con la versione
  aggiornata (non creare duplicati).
- Tutti gli orari sono fuso `Europe/Rome`.
- Mantieni un tono asciutto e funzionale: questo è uno strumento, non un
  articolo di cronaca.

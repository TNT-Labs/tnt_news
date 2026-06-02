# Compito mattutino — Bollettino pendolare

Sei un assistente che, **solo nei giorni feriali alle 7:00**, produce un
bollettino con la previsione di traffico e di meteo per il tragitto in auto
**Bergamo → San Donato Milanese**. Esegui da solo, senza supervisione, tutti i
passi seguenti.

## Variabili d'ambiente attese

Configurate nelle impostazioni della routine su `claude.ai/code/routines`,
**non nel repository**:

- `GOOGLE_MAPS_API_KEY` — una sola chiave del progetto Google Cloud, con
  abilitate **Directions API** e **Weather API**. Usata per stimare il
  tempo di percorrenza (Directions) e per il meteo (Weather).

Se la variabile **non è impostata**, ricadi sui percorsi di fallback
indicati nelle sezioni 2 e 3 (Open-Meteo + ricerca web).

## 0. Controllo del giorno

- Determina il giorno della settimana di oggi (fuso `Europe/Rome`).
- Se è **sabato o domenica**: termina subito senza produrre nulla.
- Se è un giorno feriale: prosegui.

## 1. Percorso di riferimento

Itinerario fisso (così è stato definito dall'utente):

1. **A4** da Bergamo verso ovest.
2. **Uscita Agrate Brianza** dall'A4.
3. **Viabilità ordinaria** (surface) tra Agrate e Carugate.
4. **Ingresso A51 Tangenziale Est** al casello di Carugate.
5. **A51** in direzione sud fino all'**uscita San Donato Milanese**.

Orario di partenza di riferimento: **07:30** da Bergamo.

Punti meteo di riferimento (lat/lon, fuso `Europe/Rome`):

- **Bergamo (partenza, 07:30):** 45.6983, 9.6773
- **Carugate (intorno alle 08:15):** 45.5500, 9.3000
- **San Donato Milanese (arrivo, intorno alle 08:45):** 45.4117, 9.2697

## 2. Meteo

### 2.a Primario — Google Weather API (richiede `GOOGLE_MAPS_API_KEY`)

Per ciascuno dei tre punti chiama l'endpoint orario via `Bash`:

```bash
curl -sG "https://weather.googleapis.com/v1/forecast/hours:lookup" \
  --data-urlencode "key=$GOOGLE_MAPS_API_KEY" \
  --data-urlencode "location.latitude=45.6983" \
  --data-urlencode "location.longitude=9.6773" \
  --data-urlencode "hours=4" \
  --data-urlencode "unitsSystem=METRIC"
```

(Cambia `latitude` / `longitude` per ognuno dei tre punti.)

Dalla risposta, prendi l'oggetto in `forecastHours[]` la cui
`interval.startTime` cade nell'ora di transito (07:00–08:00 per Bergamo,
08:00–09:00 per Carugate, 08:00–09:00 per San Donato). Mappa così:

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

Per ottenere la descrizione in italiano aggiungi
`--data-urlencode "languageCode=it"` alla curl.

### 2.b Fallback — Open-Meteo (senza chiave)

Se `$GOOGLE_MAPS_API_KEY` non è impostata oppure la chiamata fallisce
(es. quota esaurita, errore di rete), ripiega su Open-Meteo:

```
https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,precipitation,precipitation_probability,weather_code,wind_speed_10m,wind_gusts_10m,wind_direction_10m,visibility&timezone=Europe%2FRome&forecast_days=1
```

`weather_code` → descrizione: 0=sereno, 1-3=poco nuvoloso/nuvoloso, 45/48=nebbia,
51-67=pioggia, 71-77=neve, 80-82=rovesci, 95-99=temporale.

Se anche Open-Meteo non è raggiungibile, usa la ricerca web (iLMeteo,
3BMeteo) e segnalalo nel `weather.summary_text`.

## 3. Traffico

L'obiettivo ha due parti distinte:

- **Tempo di percorrenza** stimato con il traffico del momento → Google
  Directions API (sezione 3.0).
- **Lista di incidenti / cantieri** sulla tratta → fonti pubbliche (sezioni
  3.1-3.5). Google non espone una lista pubblica di eventi: l'effetto degli
  incidenti è già incorporato nell'ETA, ma per scriverli a parole serve un
  feed dedicato.

### 3.0 Tempo di percorrenza — Google Directions API (richiede `GOOGLE_MAPS_API_KEY`)

Una sola chiamata copre l'intero tragitto con i due waypoint imposti
(Agrate per uscire da A4, Carugate per entrare in A51):

```bash
curl -sG "https://maps.googleapis.com/maps/api/directions/json" \
  --data-urlencode "origin=Bergamo, BG, Italia" \
  --data-urlencode "destination=San Donato Milanese, MI, Italia" \
  --data-urlencode "waypoints=via:45.5849,9.3617|via:45.5523,9.3015" \
  --data-urlencode "departure_time=now" \
  --data-urlencode "traffic_model=best_guess" \
  --data-urlencode "language=it" \
  --data-urlencode "region=it" \
  --data-urlencode "key=$GOOGLE_MAPS_API_KEY"
```

Coordinate dei waypoint (pass-through, prefisso `via:`):

- **Casello A4 Agrate Brianza** (uscita): `45.5849, 9.3617`
- **Svincolo A51 Carugate** (ingresso): `45.5523, 9.3015`

Dalla risposta (`status: "OK"`), considera `routes[0].legs[]`. Con due
waypoint hai **tre legs**: A4, surface, A51. Per ogni leg leggi
`duration_in_traffic.value` (in secondi). Convertili in minuti
(`round(value/60)`) e popolale così:

| Leg | name                                       |
|-----|--------------------------------------------|
| 0   | A4 Bergamo → Agrate                        |
| 1   | Surface Agrate → Carugate                  |
| 2   | A51 Carugate → San Donato Milanese         |

`estimated_minutes` = somma dei tre, **arrotondato all'intero**.

Se la API risponde con errore o `$GOOGLE_MAPS_API_KEY` non è impostata,
ripiega sulla baseline indicata in sezione 4 e dichiaralo in
`traffic.notice`.

### 3.1 Fonti strutturate per la lista incidenti (priorità A)

- **CCISS — Viaggiare Informati** (Centro Coordinamento Informazioni
  Sicurezza Stradale, Polizia di Stato):
  - https://www.cciss.it/
  - Cerca la sezione "Eventi viabilità" / Lombardia; se trovi un feed RSS,
    leggilo con WebFetch.
- **Luceverde Lombardia** (servizio ACI, dati aggiornati sui maggiori assi):
  - https://www.luceverde.it/lombardia
  - https://www.luceverde.it/milano (per A51 / Tangenziale Est)

### 3.2 Operatori autostradali (priorità B)

- **Autostrade per l'Italia — Viabilità in tempo reale (A4 Bergamo–Milano):**
  - https://www.autostrade.it/it/traffico-in-tempo-reale
  - Pagina spesso JS-heavy: se non leggibile, prova la versione mobile o
    l'elenco eventi a livello nazionale e filtra per "A4".
- **Milano Serravalle — Tangenziali Milano (A51):**
  - https://www.serravalle.it/traffico

### 3.3 Ricerca web (priorità C, da fare sempre)

Esegui con `WebSearch` queste query (sostituisci `AAAA-MM-GG` con la data
di oggi):

- `A4 Bergamo Milano traffico AAAA-MM-GG`
- `A51 tangenziale est Milano traffico AAAA-MM-GG`
- `A4 incidente cantiere Capriate Trezzo Agrate oggi`
- `A51 chiusura Carugate Cologno San Donato oggi`

Controlla i risultati di testate locali (Bergamonews, L'Eco di Bergamo,
MilanoToday) e dei comuni interessati per eventuali avvisi di chiusura
notturna o eventi straordinari.

### 3.4 Filtri di pertinenza

Tieni solo gli eventi che ricadono nella **tratta del giorno**:

- **A4 direzione Milano (ovest)**, circa **km 145–190**.
  Uscite di interesse, dall'inizio: Bergamo, Dalmine, Capriate San Gervasio,
  Trezzo sull'Adda, Cavenago-Cambiago, Agrate Brianza.
- **A51 Tangenziale Est**, **dal casello/svincolo di Carugate
  fino all'uscita San Donato Milanese** (passando per Cologno, Vimodrone,
  Lambrate, Rogoredo).

Scarta eventi su altre direttrici o in zone fuori da questi limiti.

### 3.5 Checklist di trasparenza

Per ogni fonte consultata in 3.1 e 3.2 annota mentalmente se sei riuscito
a leggere contenuto utile. **Devi** valorizzare il campo
`traffic.notice` nel JSON nei casi seguenti:

- Se **nessuna** delle fonti 3.1 + 3.2 è risultata leggibile:
  `"notice": "Fonti incidenti strutturate non raggiungibili (CCISS, Luceverde, Autostrade, Serravalle): dato non verificato in modo strutturato; segnalazioni eventuali derivano solo da ricerca web."`
- Se solo alcune sono leggibili: indica quali, es.
  `"notice": "Solo Luceverde leggibile; CCISS e Autostrade non disponibili."`
- Se tutte raggiungibili e niente di rilevante: **non** popolare `notice`;
  lascia `incidents: []` e basta (il sito mostrerà "Nessuna segnalazione
  rilevata sulle fonti consultate").

**Non mentire mai per omissione**: se le fonti tacciono, dillo. Se non hai
controllato, non scrivere `incidents: []` senza `notice`.

## 4. Stima del tempo di percorrenza — fallback

**Da usare solo se la chiamata Google Directions (3.0) non è andata a buon
fine.** In quel caso parti dalle baseline e adegua in base agli incidenti
intercettati al punto 3:

| Segmento                                        | Baseline (min) |
|-------------------------------------------------|----------------|
| A4 Bergamo → uscita Agrate                      | 35–45          |
| Viabilità ordinaria Agrate → ingresso A51 Carugate | 12–18       |
| A51 Carugate → uscita San Donato Milanese       | 25–40          |
| **Totale**                                       | **~75–95**     |

Se ricadi qui, **valorizza `traffic.notice`** spiegando il motivo
(es. "Directions API non disponibile: stima da baseline."). Non inventare
numeri: meglio una forchetta onesta.

## 5. Verdetto moto

Applica i seguenti criteri sui valori meteo lungo l'intera finestra del
tragitto (07:30 → 09:00) **in tutti e tre i punti**:

- **`go` (Moto OK)** — tutte queste condizioni sono vere:
  - precipitazioni previste = 0 mm e probabilità < 30%
  - nessun codice meteo di nebbia (45/48), neve (71–77) o temporale (95–99)
  - visibilità ≥ 5 km (se disponibile)
  - vento medio < 25 km/h **e** raffiche < 35 km/h
  - temperatura ≥ 7 °C
  - asfalto presumibilmente asciutto (nessuna pioggia nelle 3 ore precedenti)

- **`caution` (Moto con cautela)** — non si applica `no` ma uno o più di:
  - probabilità di pioggia 30–50%
  - raffiche 35–45 km/h o vento medio 25–35 km/h
  - temperatura 4–7 °C
  - leggera umidità residua sull'asfalto

- **`no` (Niente moto)** — almeno uno di:
  - precipitazioni > 0 mm in uno qualsiasi dei tre punti nella finestra
  - probabilità di pioggia ≥ 50%
  - nebbia, neve, temporale previsti
  - vento medio > 35 km/h o raffiche > 45 km/h
  - temperatura < 4 °C
  - visibilità < 2 km

Motiva il verdetto in **2-4 ragioni concise**.

## 6. Scrivi il bollettino

Crea il file `content/bollettino/AAAA-MM-GG.json` (data di oggi) con questa
struttura esatta:

```json
{
  "date": "AAAA-MM-GG",
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
    "notice": "Solo Luceverde leggibile; CCISS e Autostrade non disponibili."
  },
  "moto": {
    "verdict": "go",
    "label": "Moto OK",
    "reasons": [
      "Niente pioggia prevista sull'intero tragitto",
      "Temperatura sopra i 7 °C",
      "Vento moderato e raffiche entro i 35 km/h"
    ]
  },
  "sources": [
    {"name": "Google Maps Directions API", "url": "https://developers.google.com/maps/documentation/directions"},
    {"name": "Google Weather API", "url": "https://developers.google.com/maps/documentation/weather"},
    {"name": "CCISS — Viaggiare Informati", "url": "https://www.cciss.it/"},
    {"name": "Luceverde Lombardia", "url": "https://www.luceverde.it/lombardia"}
  ]
}
```

Includi nella lista `sources` **solo le fonti che hai effettivamente
consultato** (con risultato utile o no, basta averle interrogate). Se hai
usato il fallback Open-Meteo / ricerca web, sostituisci di conseguenza.
Non includere mai la chiave API in `sources`, nei log, nei commit o nel
JSON: deve restare solo nella variabile d'ambiente.

Regole:
- I valori `verdict` ammessi sono **solo** `go`, `caution`, `no`.
- `label` deve combaciare: `Moto OK`, `Moto con cautela`, `Niente moto`.
- Se una fonte non era raggiungibile, **non** inventare incidenti: lascia
  `incidents: []` e popola `traffic.notice` come da 3.5.
- Il campo `traffic.notice` è **opzionale**: omettilo (o usa stringa vuota)
  solo se hai potuto consultare tutte le fonti strutturate.

## 7. Genera il sito e pubblica

```bash
python3 build.py
git add -A
git commit -m "Bollettino pendolare <data>"
git push origin HEAD:claude/main
```

Verifica che l'ambiente claude/main sia stato correttamente aggiornato.
GitHub Pages aggiornerà la pagina `/bollettino/` entro pochi minuti.

### Se il push o il merge va in conflitto

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
- Una sola esecuzione al giorno feriale. Se il file
  `content/bollettino/AAAA-MM-GG.json` esiste già per oggi, **sovrascrivilo**
  con la versione aggiornata (non creare duplicati).
- Tutti gli orari sono fuso `Europe/Rome`.
- Mantieni un tono asciutto e funzionale: questo è uno strumento, non un
  articolo di cronaca.

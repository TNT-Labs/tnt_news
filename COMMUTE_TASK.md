# Compito mattutino — Bollettino pendolare

Sei un assistente che, **solo nei giorni feriali alle 7:00**, produce un
bollettino con la previsione di traffico e di meteo per il tragitto in auto
**Bergamo → San Donato Milanese**. Esegui da solo, senza supervisione, tutti i
passi seguenti.

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

## 2. Meteo (Open-Meteo, gratis, nessuna chiave)

Per ciascuno dei tre punti scarica la previsione oraria con WebFetch:

```
https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,precipitation,precipitation_probability,weather_code,wind_speed_10m,wind_gusts_10m,wind_direction_10m,visibility&timezone=Europe%2FRome&forecast_days=1
```

Per ogni punto estrai i valori dell'ora di transito stimata (07:30 / 08:15 /
08:45). Da `weather_code` ricava una descrizione sintetica
(0=sereno, 1-3=poco nuvoloso/nuvoloso, 45/48=nebbia, 51-67=pioggia, 71-77=neve,
80-82=rovesci, 95-99=temporale).

## 3. Traffico e incidenti

L'obiettivo è intercettare cantieri, incidenti, code e chiusure **sulla tratta
del giorno**, non in tutta la Lombardia. Consulta le fonti in ordine di
priorità e tieni traccia di quali sono risultate raggiungibili (serve al
punto 3.5).

### 3.1 Fonti strutturate (priorità A)

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

## 4. Stima del tempo di percorrenza

Baseline indicative al feriale ore 07:30 (da adeguare in base a quanto trovato):

| Segmento                                        | Baseline (min) |
|-------------------------------------------------|----------------|
| A4 Bergamo → uscita Agrate                      | 35–45          |
| Viabilità ordinaria Agrate → ingresso A51 Carugate | 12–18       |
| A51 Carugate → uscita San Donato Milanese       | 25–40          |
| **Totale**                                       | **~75–95**     |

Adegua le baseline in base ai cantieri/incidenti reperiti. Se un tratto è
chiuso o gravemente rallentato, somma i tempi extra plausibili e segnala
chiaramente. Non inventare numeri: meglio una forchetta onesta.

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
    {"name": "Open-Meteo", "url": "https://open-meteo.com/"},
    {"name": "CCISS — Viaggiare Informati", "url": "https://www.cciss.it/"},
    {"name": "Luceverde Lombardia", "url": "https://www.luceverde.it/lombardia"},
    {"name": "Autostrade per l'Italia — Traffico", "url": "https://www.autostrade.it/it/traffico-in-tempo-reale"},
    {"name": "Tangenziali Milano (Milano Serravalle) — Traffico", "url": "https://www.serravalle.it/traffico"}
  ]
}
```

Includi nella lista `sources` **solo le fonti che hai effettivamente
consultato** (gettate un occhio, indipendentemente dal fatto che abbiano
prodotto risultati). Se CCISS è offline e non l'hai potuta leggere, non
metterla in `sources`.

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

GitHub Pages aggiornerà la pagina `/bollettino/` entro pochi minuti.

## Regole di qualità

- **Mai inventare**: se un dato non è disponibile, scrivilo esplicitamente.
- Una sola esecuzione al giorno feriale. Se il file
  `content/bollettino/AAAA-MM-GG.json` esiste già per oggi, **sovrascrivilo**
  con la versione aggiornata (non creare duplicati).
- Tutti gli orari sono fuso `Europe/Rome`.
- Mantieni un tono asciutto e funzionale: questo è uno strumento, non un
  articolo di cronaca.

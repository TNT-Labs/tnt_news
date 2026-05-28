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

## 3. Traffico (siti pubblici, gratis)

Controlla con WebFetch i seguenti siti per **cantieri, incidenti e code**
sulla tratta del giorno:

- **Autostrade per l'Italia (A4 tratta Bergamo–Milano):**
  https://www.autostrade.it/it/traffico-in-tempo-reale
- **Milano Serravalle – Tangenziali Milano (A51 Tangenziale Est):**
  https://www.serravalle.it/traffico
- In subordine, ricerca web per "A4 Bergamo Milano traffico oggi" e "A51
  Tangenziale Est traffico oggi".

Se i siti sono irraggiungibili, indicalo onestamente nel bollettino e usa solo
la stima baseline.

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
    ]
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
    {"name": "Autostrade per l'Italia — Traffico", "url": "https://www.autostrade.it/it/traffico-in-tempo-reale"},
    {"name": "Tangenziali Milano (Milano Serravalle) — Traffico", "url": "https://www.serravalle.it/traffico"}
  ]
}
```

Regole:
- I valori `verdict` ammessi sono **solo** `go`, `caution`, `no`.
- `label` deve combaciare: `Moto OK`, `Moto con cautela`, `Niente moto`.
- Se una fonte non era raggiungibile, **non** inventare incidenti: lascia
  `incidents: []` e segnalalo nel `summary_text`.

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

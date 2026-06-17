# TNT News

Blog sperimentale **a redazione automatica**: ogni giorno pubblica una
notizia rilevante per la **Lombardia**, con priorità alla **provincia di
Bergamo**, corredata da grafici e diagrammi. Sito statico, pubblicato su
GitHub Pages.

## Come funziona

1. Una volta al giorno, **Claude Code** esegue le istruzioni in
   [`DAILY_TASK.md`](DAILY_TASK.md): cerca la notizia del giorno, verifica le
   fonti, scrive l'articolo e genera i grafici SVG.
2. L'articolo viene salvato in `content/articles/AAAA-MM-GG-slug/`.
3. `build.py` rigenera il sito statico in `docs/`.
4. Il commit viene pushato e GitHub Pages pubblica il sito.

## Struttura del progetto

```
content/articles/<slug>/   Articoli: meta.json + body.html (+ eventuali asset)
templates/                 Template HTML del sito (base, index, articolo)
static/                    Asset statici copiati nel sito (style.css)
build.py                   Generatore del sito statico (solo Python standard)
docs/                      Sito generato — è ciò che GitHub Pages pubblica
DAILY_TASK.md              Istruzioni eseguite ogni giorno dalla redazione AI
COMMUTE_TASK.md            Bollettino pendolare nei giorni feriali alle 7:00
TARIFFE_TASK.md            Aggiornamento giornaliero dei listini delle colonnine
```

## Generare il sito in locale

```bash
python3 build.py
```

Apri poi `docs/index.html` nel browser per l'anteprima. Non servono dipendenze
esterne: basta Python 3.

## Pubblicare su GitHub Pages

1. Vai su **Settings → Pages** del repository.
2. In *Build and deployment* scegli **Deploy from a branch**.
3. Seleziona il branch desiderato e la cartella **`/docs`**, poi salva.
4. Dopo qualche minuto il sito sarà online all'indirizzo indicato da GitHub.

> Il file `docs/.nojekyll` (creato automaticamente da `build.py`) evita che
> GitHub applichi Jekyll, così il sito viene servito così com'è.

## Automazione giornaliera

L'articolo del giorno è prodotto da Claude eseguendo `DAILY_TASK.md`. Per
attivarlo ci sono due strade.

### A) Trigger schedulato di Claude Code sul web *(consigliato)*

Usa il tuo **abbonamento Claude Pro/Max**, senza costi a consumo.

- Apri questo repository in **Claude Code on the web**.
- Crea un **trigger pianificato** (es. ogni giorno alle 7:00) il cui prompt è:
  *"Esegui le istruzioni in DAILY_TASK.md"*.
- Documentazione: https://code.claude.com/docs/en/claude-code-on-the-web

### B) GitHub Action schedulata *(alternativa)*

Un workflow `cron` può eseguire `DAILY_TASK.md` ogni giorno. Per usare il piano
Pro serve configurare l'autenticazione di Claude Code; in alternativa si usa
l'**API Anthropic** (fatturata a consumo, separata dall'abbonamento Pro).

## Nota importante sull'abbonamento

L'abbonamento **Claude.ai Pro** abilita l'uso interattivo (chat e Claude Code),
**non** è un'API richiamabile da programmi esterni. L'automazione “a costo
zero” descritta sopra funziona perché Claude Code stesso si autentica con
l'abbonamento ed esegue il compito; non perché esista una API del piano Pro.

## Variabili d'ambiente

Da impostare nelle impostazioni dell'ambiente cloud Claude Code (su
`claude.ai/code/environments`), **mai nel repository**:

- `GOOGLE_MAPS_API_KEY` — Directions API + Weather API per il bollettino
  pendolare (`COMMUTE_TASK.md`). Una sola chiave del progetto Google Cloud
  con entrambe abilitate.
- `OPENCHARGEMAP_API_KEY` — chiave pubblica OpenChargeMap per la mappa
  colonnine in `/ricarica/`. Si ottiene gratis su
  https://openchargemap.org/site/profile/applications . È pensata per essere
  visibile lato client (identifica l'app, non è un segreto): `build.py` la
  inietta inline in `docs/ricarica/index.html`.

Se una variabile non è impostata, la feature corrispondente degrada
gentilmente (fallback Open-Meteo per il bollettino, messaggio di errore
sulla pagina ricarica).

## Qualità ed etica editoriale

- Una sola notizia al giorno, da **fonti verificate e citate**.
- Nessun fatto inventato: in assenza di fonti affidabili si pubblica una nota
  di servizio, non una notizia falsa.
- I contenuti sono **rielaborati**, non copiati dalle fonti.

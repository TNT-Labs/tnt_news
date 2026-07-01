#!/usr/bin/env python3
"""Generatore del sito statico TNT News.

Legge gli articoli da content/articles/<slug>/ (meta.json + body.html)
e produce il sito statico in docs/ pronto per GitHub Pages.

Nessuna dipendenza esterna: solo libreria standard di Python 3.
"""

import json
import os
import re
import shutil
import unicodedata
from datetime import date, datetime, timezone
from statistics import median
from email.utils import format_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content" / "articles"
BOLLETTINO_DIR = ROOT / "content" / "bollettino"
TARIFFE_PATH = ROOT / "content" / "tariffe.json"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "docs"

SITE_NAME = "TNT News"
SITE_DESC = "Notizie e fatti dalla Lombardia e dalla provincia di Bergamo"
SITE_URL = "https://tnt-labs.github.io/tnt_news"
OG_IMAGE = f"{SITE_URL}/og-default.png"
# Recapito per rettifiche, privacy e segnalazioni. Da personalizzare.
CONTACT = "[inserisci qui l'email di contatto del titolare]"

# Insieme chiuso di categorie usate per la navigazione (ordine canonico fisso).
# I tag liberi restano nel meta.json come semplici etichette dell'articolo.
CATEGORIES = [
    "Cronaca", "Politica", "Economia", "Trasporti",
    "Sanità", "Ambiente", "Cultura", "Sport", "Attualità",
]
CATEGORY_SET = set(CATEGORIES)
DEFAULT_CATEGORY = "Attualità"

VERDICT_LABELS = {
    "go": "Moto OK",
    "caution": "Moto con cautela",
    "no": "Niente moto",
}

DIRECTION_LABELS = {"andata": "Andata", "ritorno": "Ritorno"}
DIRECTION_TITLES = {
    "andata": "Bergamo &rarr; San Donato Milanese",
    "ritorno": "San Donato Milanese &rarr; Bergamo",
}

WEEKDAYS_IT = [
    "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica",
]

MONTHS_IT = [
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def load_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def render(template: str, **tokens: str) -> str:
    out = template
    for key, value in tokens.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def format_date_it(iso: str) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return iso
    return f"{d.day} {MONTHS_IT[d.month]} {d.year}"


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t or "categoria"


def count_phrase(n: int) -> str:
    return "1 notizia" if n == 1 else f"{n} notizie"


def normalize_time(value) -> str:
    """Riporta l'orario a HH:MM zero-padded ("9:5" -> "09:05").

    L'ordinamento degli articoli confronta stringhe: un orario non
    zero-padded finirebbe fuori posto ("9:30" > "10:00"). Orari non
    validi degradano a mezzanotte.
    """
    m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", str(value).strip())
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h < 24 and mi < 60:
            return f"{h:02d}:{mi:02d}"
    return "00:00"


def load_articles() -> list[dict]:
    """Carica e valida tutti gli articoli presenti."""
    articles = []
    if not CONTENT_DIR.exists():
        return articles
    for folder in sorted(CONTENT_DIR.iterdir()):
        meta_path = folder / "meta.json"
        body_path = folder / "body.html"
        if not (meta_path.exists() and body_path.exists()):
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["slug"] = folder.name
        meta["body"] = body_path.read_text(encoding="utf-8")
        meta.setdefault("title", "(senza titolo)")
        meta.setdefault("date", date.today().isoformat())
        meta.setdefault("summary", "")
        meta.setdefault("tags", [])
        meta.setdefault("sources", [])
        meta.setdefault("author", "Redazione TNT News (Claude)")
        meta["time"] = normalize_time(meta.get("time", "00:00"))
        if meta.get("category") not in CATEGORY_SET:
            meta["category"] = DEFAULT_CATEGORY
        articles.append(meta)
    # piu recenti in cima; "time" (HH:MM) permette di ordinare due articoli dello stesso giorno
    articles.sort(key=lambda a: a["date"] + "T" + a["time"], reverse=True)
    return articles


def categories_in_use(articles: list[dict]) -> list[str]:
    """Categorie effettivamente presenti, nell'ordine canonico fisso."""
    used = {a["category"] for a in articles}
    return [c for c in CATEGORIES if c in used]


def render_article_taxonomy(article: dict, prefix: str) -> str:
    """Categoria (cliccabile) + tag liberi (etichette) in testa all'articolo."""
    cat = article["category"]
    parts = [
        f'<a class="tag tag-cat" href="{prefix}categorie/{slugify(cat)}/">{escape(cat)}</a>'
    ]
    parts += [f'<span class="tag">{escape(t)}</span>' for t in article["tags"]]
    return f'<div class="tags">{"".join(parts)}</div>'


def render_categories_nav(categories: list[str], prefix: str) -> str:
    if not categories:
        return ""
    links = "".join(
        f'<a href="{prefix}categorie/{slugify(c)}/">{escape(c)}</a>' for c in categories
    )
    return (
        '<nav class="cat-nav" aria-label="Categorie">'
        f'<span class="cat-nav-label">Categorie:</span> {links}</nav>'
    )


def render_sources(sources: list) -> str:
    if not sources:
        return ""
    items = []
    for s in sources:
        if isinstance(s, dict):
            name = escape(s.get("name", s.get("url", "fonte")))
            url = s.get("url", "")
        else:
            name, url = escape(str(s)), ""
        if url:
            items.append(f'<li><a href="{escape(url)}" rel="noopener" target="_blank">{name}</a></li>')
        else:
            items.append(f"<li>{name}</li>")
    return (
        '<section class="sources"><h2>Fonti</h2><ul>'
        + "".join(items)
        + "</ul></section>"
    )


def render_card(a: dict, prefix: str, featured: bool = False) -> str:
    url = f"{prefix}articoli/{a['slug']}/"
    cls = "card featured" if featured else "card"
    blob = escape(
        " ".join([a["title"], a["summary"], a["category"], " ".join(a["tags"])]).lower()
    )
    return (
        f'<article class="{cls}" data-search="{blob}" data-cat="{escape(a["category"])}">'
        f'<a class="card-link" href="{escape(url)}">'
        f'<div class="card-body">'
        f'<div class="tags"><span class="tag">{escape(a["category"])}</span></div>'
        f'<h2 class="card-title">{escape(a["title"])}</h2>'
        f'<p class="card-summary">{escape(a["summary"])}</p>'
        f'<p class="card-meta">{format_date_it(a["date"])}</p>'
        f"</div></a></article>"
    )


def related_articles(article: dict, articles: list[dict], limit: int = 3) -> list[dict]:
    tagset = set(article["tags"])
    cat = article["category"]
    others = [a for a in articles if a["slug"] != article["slug"]]
    others.sort(
        key=lambda a: (a["category"] == cat, len(tagset & set(a["tags"])), a["date"]),
        reverse=True,
    )
    return others[:limit]


def render_related(article: dict, articles: list[dict], prefix: str) -> str:
    related = related_articles(article, articles)
    if not related:
        return ""
    cards = "".join(render_card(a, prefix) for a in related)
    return (
        '<section class="related"><h2>Altre notizie</h2>'
        f'<div class="card-grid">{cards}</div></section>'
    )


def page(base: str, *, title: str, description: str, root: str, canonical: str,
         og_type: str, categories: str, content: str) -> str:
    """Assembla una pagina completa con i meta tag SEO/social."""
    return render(
        base,
        TITLE=title,
        DESCRIPTION=description,
        ROOT=root,
        CANONICAL=escape(canonical),
        OG_TYPE=og_type,
        OG_IMAGE=escape(OG_IMAGE),
        CATEGORIES=categories,
        CONTENT=content,
    )


def build_article_page(article: dict, articles: list[dict], categories: list[str], base: str) -> str:
    prefix = "../../"
    article_tpl = load_template("article.html")
    content = render(
        article_tpl,
        TITLE=escape(article["title"]),
        DATE_HUMAN=format_date_it(article["date"]),
        DATE_ISO=escape(article["date"]),
        AUTHOR=escape(article["author"]),
        TAGS=render_article_taxonomy(article, prefix),
        SUMMARY=escape(article["summary"]),
        BODY=article["body"],
        SOURCES=render_sources(article["sources"]),
        RELATED=render_related(article, articles, prefix),
    )
    return page(
        base,
        title=escape(article["title"]) + " — " + SITE_NAME,
        description=escape(article["summary"] or SITE_DESC),
        root=prefix,
        canonical=f"{SITE_URL}/articoli/{article['slug']}/",
        og_type="article",
        categories=render_categories_nav(categories, prefix),
        content=content,
    )


def build_category_page(category: str, articles: list[dict], categories: list[str], base: str) -> str:
    prefix = "../../"
    items = [a for a in articles if a["category"] == category]
    cards = "".join(render_card(a, prefix) for a in items)
    content = (
        f'<a class="back-link" href="{prefix}index.html">&larr; Tutte le notizie</a>'
        f'<section class="hero-intro"><h1>Categoria: {escape(category)}</h1>'
        f"<p>{count_phrase(len(items))} in questa categoria.</p></section>"
        f'<div class="card-grid">{cards}</div>'
    )
    return page(
        base,
        title=f"{escape(category)} — {SITE_NAME}",
        description=escape(f"Notizie nella categoria {category} su {SITE_NAME}"),
        root=prefix,
        canonical=f"{SITE_URL}/categorie/{slugify(category)}/",
        og_type="website",
        categories=render_categories_nav(categories, prefix),
        content=content,
    )


def build_index_page(articles: list[dict], categories: list[str], base: str) -> str:
    index_tpl = load_template("index.html")
    if not articles:
        content = render(
            index_tpl,
            TAGFILTERS="",
            CARDS='<p class="empty">Nessun articolo ancora pubblicato.</p>',
        )
    else:
        filters = [
            '<button type="button" class="tag-filter is-active" data-cat="all">Tutte</button>'
        ]
        for c in categories:
            filters.append(
                f'<button type="button" class="tag-filter" data-cat="{escape(c)}">{escape(c)}</button>'
            )
        tagfilters = "".join(filters)

        cards_html = [render_card(a, "", featured=(i == 0)) for i, a in enumerate(articles)]
        cards = '<div class="card-grid" id="cardGrid">' + "".join(cards_html) + "</div>"
        content = render(index_tpl, TAGFILTERS=tagfilters, CARDS=cards)
    return page(
        base,
        title=SITE_NAME + " — " + SITE_DESC,
        description=escape(SITE_DESC),
        root="",
        canonical=f"{SITE_URL}/",
        og_type="website",
        categories=render_categories_nav(categories, ""),
        content=content,
    )


def build_simple_page(slug: str, title: str, body: str, categories: list[str], base: str) -> str:
    prefix = "../"
    content = (
        f'<a class="back-link" href="{prefix}index.html">&larr; Home</a>{body}'
    )
    return page(
        base,
        title=f"{escape(title)} — {SITE_NAME}",
        description=escape(f"{title} — {SITE_NAME}"),
        root=prefix,
        canonical=f"{SITE_URL}/{slug}/",
        og_type="website",
        categories=render_categories_nav(categories, prefix),
        content=content,
    )


def build_feed(articles: list[dict]) -> str:
    items = []
    latest = None
    for a in articles:
        link = f"{SITE_URL}/articoli/{a['slug']}/"
        try:
            d = datetime.strptime(f"{a['date']}T{a['time']}", "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            d = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if latest is None or d > latest:
            latest = d
        items.append(
            "<item>"
            f"<title>{escape(a['title'])}</title>"
            f"<link>{escape(link)}</link>"
            f'<guid isPermaLink="true">{escape(link)}</guid>'
            f"<pubDate>{format_datetime(d)}</pubDate>"
            f"<description>{escape(a['summary'])}</description>"
            "</item>"
        )
    # lastBuildDate deterministico: data dell'articolo piu recente.
    # Evita conflitti di merge quando la routine bollettino rigenera docs/.
    last_build = format_datetime(latest or datetime(1970, 1, 1, tzinfo=timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{escape(SITE_NAME)}</title>"
        f"<link>{SITE_URL}/</link>"
        f"<description>{escape(SITE_DESC)}</description>"
        "<language>it-it</language>"
        f"<lastBuildDate>{last_build}</lastBuildDate>"
        f'<atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>'
        + "".join(items)
        + "</channel></rss>\n"
    )


def about_body() -> str:
    return (
        '<article class="article">'
        '<header class="article-header"><h1>Chi siamo</h1>'
        '<p class="article-summary">TNT News è un blog sperimentale a redazione '
        "automatica dedicato alla Lombardia e alla provincia di Bergamo.</p></header>"
        '<div class="article-body">'
        "<p>TNT News pubblica ogni giorno una notizia rilevante per il territorio, "
        "raccontata in modo chiaro e corredata da grafici e dati.</p>"
        "<h2>Come nascono gli articoli</h2>"
        "<p>I contenuti sono selezionati, scritti e illustrati in modo automatico da un "
        "sistema di intelligenza artificiale (Claude, di Anthropic), senza intervento "
        "umano sui singoli articoli. Il sistema individua la notizia del giorno, ne "
        "verifica gli elementi essenziali sulle fonti pubbliche e prepara il pezzo con i "
        "relativi grafici.</p>"
        "<h2>Trasparenza</h2>"
        "<p>Indichiamo chiaramente che gli articoli di questo sito sono prodotti "
        "automaticamente da un'intelligenza artificiale. È una scelta di trasparenza nei "
        "confronti dei lettori.</p>"
        "<h2>Fonti e accuratezza</h2>"
        "<p>Ogni articolo riporta le fonti utilizzate, rielaborate con parole proprie. "
        "Nonostante i controlli, i testi automatici possono contenere imprecisioni: "
        "invitiamo a verificare sempre sulle fonti originali e a segnalarci eventuali "
        "errori.</p>"
        "<h2>Contatti e rettifiche</h2>"
        f"<p>Per segnalazioni, richieste di rettifica o rimozione: {escape(CONTACT)}. "
        'Consulta anche le <a href="../note-legali/">Note legali e privacy</a>.</p>'
        "</div></article>"
    )


def legal_body() -> str:
    return (
        '<article class="article">'
        '<header class="article-header"><h1>Note legali e privacy</h1>'
        '<p class="article-summary">Informazioni su titolarità, trattamento dei dati, '
        "cookie, diritto d'autore e responsabilità.</p></header>"
        '<div class="article-body">'
        "<h2>Titolare del sito</h2>"
        f"<p>Il sito è gestito da [nome o ragione sociale del titolare]. Per qualsiasi "
        f"comunicazione: {escape(CONTACT)}.</p>"
        "<h2>Natura dei contenuti</h2>"
        "<p>TNT News è un blog sperimentale i cui articoli sono generati "
        "automaticamente da un sistema di intelligenza artificiale, senza supervisione "
        "redazionale sui singoli contenuti. I testi hanno finalità informativa e possono "
        "contenere errori o imprecisioni.</p>"
        "<h2>Privacy (Reg. UE 2016/679 - GDPR)</h2>"
        "<p>Questo sito non raccoglie dati personali tramite moduli, non utilizza cookie "
        "di profilazione né strumenti di analisi o tracciamento di terze parti. L'unico "
        "dato salvato sul dispositivo è una preferenza tecnica (tema chiaro/scuro) "
        "conservata nella memoria locale del browser (localStorage): resta sul tuo "
        "dispositivo, non viene trasmessa e non richiede consenso.</p>"
        "<p>Il sito è ospitato su GitHub Pages (GitHub, Inc.). Il fornitore di hosting "
        "può raccogliere automaticamente log tecnici (incluso l'indirizzo IP) per "
        "finalità di sicurezza e funzionamento del servizio. Per esercitare i diritti "
        f"previsti dagli artt. 15-22 GDPR puoi scrivere a {escape(CONTACT)}.</p>"
        "<h2>Cookie</h2>"
        "<p>Il sito non installa cookie. Utilizza esclusivamente il localStorage per la "
        "preferenza di tema, esente da consenso secondo le linee guida del Garante per la "
        "protezione dei dati personali.</p>"
        "<h2>Diritto d'autore</h2>"
        "<p>Le notizie sono rielaborate con parole proprie a partire da fonti pubbliche, "
        "sempre citate; i grafici sono elaborazioni originali. Non vengono riprodotti "
        "integralmente articoli di terzi. Se ritieni che un contenuto violi un tuo "
        f"diritto, segnalalo a {escape(CONTACT)}: verificheremo e, se necessario, "
        "rimuoveremo il contenuto.</p>"
        "<h2>Responsabilità e diritto di rettifica</h2>"
        "<p>I contenuti sono forniti “così come sono”, senza garanzie di "
        "completezza o accuratezza. Chiunque ritenga lesi i propri diritti o riscontri "
        f"inesattezze può chiedere rettifica o rimozione scrivendo a {escape(CONTACT)}; "
        "le richieste fondate saranno gestite tempestivamente.</p>"
        "<h2>Legge applicabile</h2>"
        "<p>Il sito è soggetto alla legge italiana.</p>"
        '<p class="legal-disclaimer"><em>Questo testo è un modello informativo e non '
        "costituisce consulenza legale. Per una pubblicazione regolare si raccomanda una "
        "verifica con un professionista, in particolare riguardo agli obblighi sulla "
        "registrazione delle testate e alla responsabilità editoriale.</em></p>"
        "</div></article>"
    )


# --- Bollettino pendolare ---------------------------------------------------

def load_bollettini() -> list[dict]:
    items: list[dict] = []
    if not BOLLETTINO_DIR.exists():
        return items
    for f in sorted(BOLLETTINO_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data["slug"] = f.stem
        if data.get("direction") not in DIRECTION_LABELS:
            data["direction"] = "ritorno" if f.stem.endswith("-ritorno") else "andata"
        data.setdefault("date", f.stem.removesuffix("-ritorno"))
        items.append(data)
    # piu recenti in cima; a parita di data il ritorno (pubblicato dopo) precede
    items.sort(key=lambda b: (b["date"], b["direction"] == "ritorno"), reverse=True)
    return items


def render_weather_cards(weather: dict) -> str:
    pts = (weather or {}).get("by_point") or []
    if not pts:
        return ""
    out = ['<div class="weather-grid">']
    for p in pts:
        parts = []
        if p.get("temp_c") is not None:
            parts.append(f'<span>{escape(str(p["temp_c"]))}°C</span>')
        if p.get("precip_mm") is not None:
            parts.append(f'<span>{escape(str(p["precip_mm"]))} mm</span>')
        if p.get("wind_kmh") is not None:
            wd = p.get("wind_dir")
            wd_str = f' {escape(str(wd))}' if wd else ""
            parts.append(f'<span>{escape(str(p["wind_kmh"]))} km/h{wd_str}</span>')
        out.append(
            '<div class="weather-card">'
            f'<p class="weather-where">{escape(str(p.get("name", "")))}</p>'
            f'<p class="weather-cond">{escape(str(p.get("cond", "")))}</p>'
            f'<p class="weather-data">{" · ".join(parts)}</p>'
            '</div>'
        )
    out.append('</div>')
    return "".join(out)


def render_traffic_segments(traffic: dict) -> str:
    segs = (traffic or {}).get("segments") or []
    if not segs:
        return ""
    rows = "".join(
        '<tr>'
        f'<td>{escape(str(s.get("name", "")))}</td>'
        f'<td class="num">{escape(str(s.get("minutes", "")))} min</td>'
        '</tr>'
        for s in segs
    )
    return f'<table class="traffic-table"><tbody>{rows}</tbody></table>'


def render_incidents(traffic: dict) -> str:
    t = traffic or {}
    items = t.get("incidents") or []
    notice = (t.get("notice") or "").strip()
    debug = (t.get("debug") or "").strip()
    parts: list[str] = []
    if notice:
        parts.append(f'<p class="incidents-notice">⚠ {escape(notice)}</p>')
    if items:
        lis = "".join(
            f'<li><strong>{escape(str(it.get("where", "")))}:</strong> {escape(str(it.get("desc", "")))}</li>'
            for it in items
        )
        parts.append(f'<ul class="incidents">{lis}</ul>')
    elif not notice:
        parts.append(
            '<p class="incidents-none">Nessuna segnalazione rilevata sulle fonti consultate.</p>'
        )
    if debug:
        parts.append(
            '<details class="incidents-debug">'
            "<summary>Dettagli tecnici sulla raccolta dati</summary>"
            f"<p>{escape(debug)}</p></details>"
        )
    return "".join(parts)


def render_verdict(moto: dict) -> str:
    m = moto or {}
    v = m.get("verdict", "no")
    if v not in ("go", "caution", "no"):
        v = "no"
    label = m.get("label") or VERDICT_LABELS[v]
    reasons = m.get("reasons") or []
    rs = "".join(f"<li>{escape(str(r))}</li>" for r in reasons)
    return (
        f'<section class="verdict verdict-{v}">'
        f'<p class="verdict-label">{escape(str(label))}</p>'
        + (f'<ul class="verdict-reasons">{rs}</ul>' if rs else "")
        + "</section>"
    )


def render_bollettino_history(items: list[dict], prefix: str, exclude_slug: str | None = None) -> str:
    rows = []
    for b in items:
        if b.get("slug") == exclude_slug:
            continue
        if len(rows) >= 7:
            break
        v = (b.get("moto") or {}).get("verdict", "no")
        if v not in ("go", "caution", "no"):
            v = "no"
        label = (b.get("moto") or {}).get("label") or VERDICT_LABELS[v]
        minutes = (b.get("traffic") or {}).get("estimated_minutes")
        time_html = (
            f'<span class="hist-time">{escape(str(minutes))} min</span>'
            if minutes is not None else ""
        )
        rows.append(
            f'<li><a href="{prefix}bollettino/{escape(b["slug"])}/">'
            f'<span class="hist-date">{format_date_it(b["date"])}</span>'
            f'<span class="hist-dir">{DIRECTION_LABELS[b["direction"]]}</span>'
            f'<span class="hist-verdict verdict-{v}">{escape(str(label))}</span>'
            f'{time_html}'
            '</a></li>'
        )
    if not rows:
        return ""
    return (
        '<section class="bollettino-history">'
        '<h2>Ultimi bollettini</h2>'
        f'<ul>{"".join(rows)}</ul>'
        "</section>"
    )


def render_bollettino_trend(data: dict, items: list[dict]) -> str:
    """Sparkline dei tempi delle ultime corse (stessa direzione) e confronto
    del tempo di oggi con la mediana storica dello stesso giorno feriale."""
    direction = data.get("direction", "andata")
    current = (data.get("traffic") or {}).get("estimated_minutes")
    if current is None:
        return ""
    history = [
        b for b in items
        if b.get("direction") == direction
        and b.get("slug") != data.get("slug")
        and b.get("date", "") < data.get("date", "9999")
        and (b.get("traffic") or {}).get("estimated_minutes") is not None
    ]
    history.sort(key=lambda b: b["date"])
    points = [(b["date"], int(b["traffic"]["estimated_minutes"])) for b in history[-14:]]
    points.append((data["date"], int(current)))
    if len(points) < 3:
        return ""

    try:
        weekday = datetime.strptime(data["date"], "%Y-%m-%d").weekday()
    except ValueError:
        weekday = None
    same_day = [
        int(b["traffic"]["estimated_minutes"]) for b in history
        if weekday is not None
        and datetime.strptime(b["date"], "%Y-%m-%d").weekday() == weekday
    ]
    if len(same_day) >= 3:
        ref = median(same_day)
        ref_desc = (
            f"degli ultimi {WEEKDAYS_IT[weekday]} "
            f"({round(ref)} min su {len(same_day)} corse)"
        )
    else:
        vals_prev = [m for _, m in points[:-1]]
        ref = median(vals_prev)
        ref_desc = f"delle ultime {len(vals_prev)} corse ({round(ref)} min)"
    delta = current - ref
    if abs(delta) <= 2:
        compare = f"in linea con la mediana {ref_desc}"
    else:
        sign = "+" if delta > 0 else "−"
        compare = f"{sign}{round(abs(delta))} min rispetto alla mediana {ref_desc}"
    compare_html = (
        f'<p class="trend-compare">Oggi <strong>{current} min</strong>: '
        f"{escape(compare)}.</p>"
    )

    w, h = 640, 150
    pad_l, pad_r, pad_t, pad_b = 46, 16, 14, 28
    vals = [m for _, m in points]
    lo, hi = min(vals), max(vals)
    span = max(hi - lo, 1)

    def x(i: int) -> float:
        return pad_l + i * (w - pad_l - pad_r) / (len(points) - 1)

    def y(v: float) -> float:
        return pad_t + (hi - v) * (h - pad_t - pad_b) / span

    poly = " ".join(f"{x(i):.1f},{y(m):.1f}" for i, (_, m) in enumerate(points))
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(m):.1f}" r="3" class="trend-dot"/>'
        for i, (_, m) in enumerate(points[:-1])
    )
    aria = (
        f"Tempi di percorrenza delle ultime {len(points)} corse "
        f"({DIRECTION_LABELS[direction].lower()}), da {lo} a {hi} minuti; "
        f"oggi {current} minuti."
    )
    svg = (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(aria)}" class="trend-svg">'
        f'<line x1="{pad_l}" y1="{y(hi):.1f}" x2="{w - pad_r}" y2="{y(hi):.1f}" class="trend-grid"/>'
        f'<line x1="{pad_l}" y1="{y(lo):.1f}" x2="{w - pad_r}" y2="{y(lo):.1f}" class="trend-grid"/>'
        f'<text x="{pad_l - 8}" y="{y(hi) + 4:.1f}" text-anchor="end" class="trend-axis">{hi}</text>'
        f'<text x="{pad_l - 8}" y="{y(lo) + 4:.1f}" text-anchor="end" class="trend-axis">{lo}</text>'
        f'<polyline points="{poly}" class="trend-line"/>'
        f"{dots}"
        f'<circle cx="{x(len(points) - 1):.1f}" cy="{y(current):.1f}" r="5" class="trend-dot-today"/>'
        f'<text x="{pad_l}" y="{h - 8}" class="trend-axis">{escape(format_date_it(points[0][0]))}</text>'
        f'<text x="{w - pad_r}" y="{h - 8}" text-anchor="end" class="trend-axis">oggi</text>'
        "</svg>"
    )
    return (
        '<section class="bollettino-section bollettino-trend">'
        "<h2>Andamento</h2>"
        + compare_html
        + f'<figure class="trend-figure">{svg}'
        f"<figcaption>Tempo totale stimato nelle ultime {len(points)} corse "
        f"di {DIRECTION_LABELS[direction].lower()}.</figcaption></figure>"
        "</section>"
    )


def build_bollettino_page(
    data: dict,
    history: list[dict],
    categories: list[str],
    base: str,
    *,
    is_archive: bool = False,
) -> str:
    prefix = "../../" if is_archive else "../"
    date_iso = data["date"]
    slug = data.get("slug", date_iso)
    direction = data.get("direction", "andata")
    dir_label = DIRECTION_LABELS[direction]
    weather = data.get("weather") or {}
    traffic = data.get("traffic") or {}
    travel = traffic.get("estimated_minutes")
    departure = escape(str(data.get("departure", "07:30")))
    route_txt = escape(str(data.get("route", "Bergamo → San Donato Milanese")))
    weather_summary = escape(weather.get("summary_text", "") or "")
    travel_html = (
        f"<strong>{escape(str(travel))} min</strong>"
        if travel is not None else "<em>non disponibile</em>"
    )

    # link alla corsa opposta dello stesso giorno, se pubblicata
    counterpart = next(
        (b for b in history if b.get("date") == date_iso and b.get("slug") != slug),
        None,
    )
    alt_html = ""
    if counterpart:
        alt_dir = counterpart.get("direction", "andata")
        alt_txt = "del ritorno" if alt_dir == "ritorno" else "dell'andata"
        alt_html = (
            f'<p class="bollettino-alt"><a href="{prefix}bollettino/'
            f'{escape(counterpart["slug"])}/">Vedi il bollettino {alt_txt} '
            "dello stesso giorno &rarr;</a></p>"
        )

    if is_archive:
        top_link = f'<a class="back-link" href="{prefix}bollettino/">&larr; Bollettino di oggi</a>'
        history_html = ""
        trend_html = ""
        feed_html = ""
    else:
        top_link = f'<a class="back-link" href="{prefix}index.html">&larr; Home</a>'
        history_html = render_bollettino_history(history, prefix, exclude_slug=slug)
        trend_html = render_bollettino_trend(data, history)
        feed_html = (
            f'<p class="bollettino-feed"><a href="{prefix}bollettino/feed.xml">'
            "Feed RSS del bollettino</a></p>"
        )

    parts = [
        top_link,
        '<article class="bollettino">',
        '<header class="bollettino-header">',
        f'<p class="bollettino-meta">Bollettino pendolare · {dir_label} · {format_date_it(date_iso)}</p>',
        f'<h1>{DIRECTION_TITLES[direction]}</h1>',
        f'<p class="bollettino-route">{route_txt}</p>',
        alt_html,
        '</header>',
        render_verdict(data.get("moto")),
        '<section class="bollettino-section">',
        '<h2>Tempo stimato in auto</h2>',
        f'<p class="travel-time">{travel_html} <span class="travel-meta">· partenza prevista {departure}</span></p>',
        render_traffic_segments(traffic),
        '<h3>Segnalazioni su A4 / A51</h3>',
        render_incidents(traffic),
        '</section>',
        trend_html,
        '<section class="bollettino-section">',
        '<h2>Meteo lungo il percorso</h2>',
        render_weather_cards(weather),
        f'<p class="weather-summary">{weather_summary}</p>' if weather_summary else "",
        '</section>',
        render_sources(data.get("sources", [])),
        feed_html,
        '</article>',
        history_html,
    ]
    content = "".join(p for p in parts if p)

    canonical = (
        f"{SITE_URL}/bollettino/{slug}/" if is_archive
        else f"{SITE_URL}/bollettino/"
    )
    verdict_label = (data.get("moto") or {}).get("label") or "Bollettino pendolare"
    desc = (
        f"{dir_label}: {verdict_label} — {travel} min stimati"
        if travel is not None else f"{dir_label}: {verdict_label}"
    )
    return page(
        base,
        title=f"Bollettino pendolare {dir_label.lower()} {format_date_it(date_iso)} — {SITE_NAME}",
        description=escape(desc),
        root=prefix,
        canonical=canonical,
        og_type="website",
        categories=render_categories_nav(categories, prefix),
        content=content,
    )


def load_tariffe() -> dict:
    if not TARIFFE_PATH.exists():
        return {"ultimo_aggiornamento": "", "gestori": []}
    try:
        return json.loads(TARIFFE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"ultimo_aggiornamento": "", "gestori": []}


def _tariff_class(tipo: str) -> str | None:
    """Classifica una riga di listino nelle colonne AC / DC / HPC."""
    t = tipo.strip().upper()
    if t.startswith("AC"):
        return "ac"
    if t.startswith("DC"):
        return "dc"
    if t.startswith("HPC"):
        return "hpc"
    return None


def _price_lower_bound(prezzo: str) -> float | None:
    """Estrae il limite inferiore del prezzo ("0,52–0,74 €/kWh" -> 0.52)."""
    m = re.search(r"(\d+),(\d+)", prezzo)
    if not m:
        return None
    return float(f"{m.group(1)}.{m.group(2)}")


def render_tariffe_table(tariffe: dict) -> str:
    """Tabella comparativa dei listini pay-per-use, una riga per gestore."""
    gestori = tariffe.get("gestori", [])
    if not gestori:
        return ""

    columns = [("ac", "AC ≤22 kW"), ("dc", "DC 22–150 kW"), ("hpc", "HPC >150 kW")]
    rows = []
    for g in sorted(gestori, key=lambda g: g.get("nome", "").lower()):
        prezzi: dict[str, str] = {}
        for r in g.get("tariffe", []):
            cls = _tariff_class(r.get("tipo", ""))
            if cls and cls not in prezzi:
                prezzi[cls] = r.get("prezzo", "")
        if prezzi:
            rows.append((g, prezzi))
    if not rows:
        return ""

    # Prezzo minimo per colonna (sul limite inferiore) per evidenziare il piu economico.
    best: dict[str, float] = {}
    for _, prezzi in rows:
        for cls, prezzo in prezzi.items():
            v = _price_lower_bound(prezzo)
            if v is not None and (cls not in best or v < best[cls]):
                best[cls] = v

    head = "".join(f'<th scope="col">{escape(label)}</th>' for _, label in columns)
    body = []
    for g, prezzi in rows:
        nome = escape(g.get("nome", ""))
        sito = g.get("sito", "")
        note = g.get("note", "")
        name_html = (
            f'<a href="{escape(sito)}" target="_blank" rel="noopener">{nome}</a>'
            if sito else nome
        )
        if note:
            name_html += ' <span class="tariff-compare-note" title="' + escape(note) + '">*</span>'
        cells = []
        for cls, _ in columns:
            prezzo = prezzi.get(cls)
            if not prezzo:
                cells.append('<td class="num empty">—</td>')
                continue
            v = _price_lower_bound(prezzo)
            is_best = v is not None and cls in best and v == best[cls]
            cells.append(
                f'<td class="num{" is-best" if is_best else ""}">{escape(prezzo)}</td>'
            )
        body.append(f'<tr><th scope="row">{name_html}</th>{"".join(cells)}</tr>')

    aggiornamento = tariffe.get("ultimo_aggiornamento", "")
    footer = (
        '<p class="tariff-compare-foot">Prezzi pay-per-use dall\'app del gestore, '
        "senza abbonamento; in grassetto verde il più basso per fascia. "
        "L'asterisco segnala condizioni particolari (passa il mouse per leggerle). "
        + (f"Aggiornato al {escape(format_date_it(aggiornamento))}." if aggiornamento else "")
        + "</p>"
    )
    return (
        '<section class="tariff-compare-section" id="listini">'
        "<h2>Listini a confronto</h2>"
        '<div class="tariff-compare-wrap">'
        '<table class="tariff-compare">'
        f'<thead><tr><th scope="col">Gestore</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        "</table></div>"
        + footer
        + "</section>"
    )


def build_ricarica_page(tariffe: dict, categories: list[str], base: str) -> str:
    prefix = "../"
    ricarica_tpl = load_template("ricarica.html")
    # JSON serializzato senza caratteri pericolosi per essere infilato in <script>.
    tariffe_json = json.dumps(tariffe, ensure_ascii=False).replace("</", "<\\/")
    # Chiave pubblica OpenChargeMap, letta da variabile d'ambiente al build.
    # E' pensata per essere visibile lato client (identifica l'app, non e' un segreto).
    ocm_key = os.environ.get("OPENCHARGEMAP_API_KEY", "").strip()
    content = render(ricarica_tpl, ROOT=prefix, TARIFFE_JSON=tariffe_json,
                     TARIFFE_TABLE=render_tariffe_table(tariffe),
                     OCM_KEY=json.dumps(ocm_key))
    return page(
        base,
        title=f"Colonnine di ricarica in Lombardia — {SITE_NAME}",
        description=escape(
            "Mappa interattiva delle colonnine elettriche in Lombardia con il "
            "listino occasionale del CPO proprietario."
        ),
        root=prefix,
        canonical=f"{SITE_URL}/ricarica/",
        og_type="website",
        categories=render_categories_nav(categories, prefix),
        content=content,
    )


def build_bollettino_feed(items: list[dict]) -> str:
    """Feed RSS dedicato al bollettino pendolare (ultime 30 corse)."""
    rss_items = []
    latest = None
    for b in items[:30]:
        link = f"{SITE_URL}/bollettino/{b['slug']}/"
        try:
            d = datetime.strptime(
                f"{b['date']}T{b.get('departure', '07:30')}", "%Y-%m-%dT%H:%M"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            d = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if latest is None or d > latest:
            latest = d
        moto = b.get("moto") or {}
        v = moto.get("verdict", "no")
        label = moto.get("label") or VERDICT_LABELS.get(v, VERDICT_LABELS["no"])
        minutes = (b.get("traffic") or {}).get("estimated_minutes")
        min_txt = f", {minutes} min stimati" if minutes is not None else ""
        title = (
            f"Bollettino {DIRECTION_LABELS[b['direction']].lower()} "
            f"{format_date_it(b['date'])}: {label}{min_txt}"
        )
        desc = (b.get("weather") or {}).get("summary_text", "") or label
        rss_items.append(
            "<item>"
            f"<title>{escape(title)}</title>"
            f"<link>{escape(link)}</link>"
            f'<guid isPermaLink="true">{escape(link)}</guid>'
            f"<pubDate>{format_datetime(d)}</pubDate>"
            f"<description>{escape(desc)}</description>"
            "</item>"
        )
    # lastBuildDate deterministico (corsa piu recente) per evitare conflitti in docs/
    last_build = format_datetime(latest or datetime(1970, 1, 1, tzinfo=timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{escape(SITE_NAME)} — Bollettino pendolare</title>"
        f"<link>{SITE_URL}/bollettino/</link>"
        "<description>Previsioni di traffico e meteo per il pendolare "
        "Bergamo–San Donato Milanese, andata e ritorno</description>"
        "<language>it-it</language>"
        f"<lastBuildDate>{last_build}</lastBuildDate>"
        f'<atom:link href="{SITE_URL}/bollettino/feed.xml" rel="self" type="application/rss+xml"/>'
        + "".join(rss_items)
        + "</channel></rss>\n"
    )


def build_empty_bollettino_page(categories: list[str], base: str) -> str:
    prefix = "../"
    content = (
        f'<a class="back-link" href="{prefix}index.html">&larr; Home</a>'
        '<article class="bollettino">'
        '<header class="bollettino-header">'
        '<p class="bollettino-meta">Bollettino pendolare</p>'
        '<h1>Bergamo &rarr; San Donato Milanese</h1>'
        '</header>'
        '<p class="empty">Nessun bollettino ancora pubblicato. Il prossimo verr&agrave; '
        'generato il prossimo giorno feriale (andata al mattino, ritorno nel '
        'pomeriggio).</p>'
        '</article>'
    )
    return page(
        base,
        title=f"Bollettino pendolare — {SITE_NAME}",
        description=escape("Bollettino pendolare Bergamo → San Donato Milanese"),
        root=prefix,
        canonical=f"{SITE_URL}/bollettino/",
        og_type="website",
        categories=render_categories_nav(categories, prefix),
        content=content,
    )


def main() -> None:
    base = load_template("base.html")
    articles = load_articles()
    cats = categories_in_use(articles)

    # pulizia output (la cartella docs e dedicata al sito generato)
    if OUTPUT_DIR.exists():
        for child in OUTPUT_DIR.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    (OUTPUT_DIR / "articoli").mkdir(parents=True, exist_ok=True)

    # asset statici
    if STATIC_DIR.exists():
        for item in STATIC_DIR.iterdir():
            if item.is_file():
                shutil.copy2(item, OUTPUT_DIR / item.name)
    # evita che GitHub Pages applichi Jekyll
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # pagina indice
    (OUTPUT_DIR / "index.html").write_text(
        build_index_page(articles, cats, base), encoding="utf-8"
    )

    # pagine articolo
    for a in articles:
        dest = OUTPUT_DIR / "articoli" / a["slug"]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(
            build_article_page(a, articles, cats, base), encoding="utf-8"
        )

    # pagine categoria
    for c in cats:
        dest = OUTPUT_DIR / "categorie" / slugify(c)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(
            build_category_page(c, articles, cats, base), encoding="utf-8"
        )

    # pagine informative
    for slug, title, body in [
        ("chi-siamo", "Chi siamo", about_body()),
        ("note-legali", "Note legali e privacy", legal_body()),
    ]:
        dest = OUTPUT_DIR / slug
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(
            build_simple_page(slug, title, body, cats, base), encoding="utf-8"
        )

    # bollettino pendolare (fuori dal feed e dall'archivio articoli)
    bollettini = load_bollettini()
    bdir = OUTPUT_DIR / "bollettino"
    bdir.mkdir(parents=True, exist_ok=True)
    if bollettini:
        for b in bollettini:
            d = bdir / b["slug"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(
                build_bollettino_page(b, bollettini, cats, base, is_archive=True),
                encoding="utf-8",
            )
        (bdir / "index.html").write_text(
            build_bollettino_page(bollettini[0], bollettini, cats, base, is_archive=False),
            encoding="utf-8",
        )
        (bdir / "feed.xml").write_text(
            build_bollettino_feed(bollettini), encoding="utf-8"
        )
    else:
        (bdir / "index.html").write_text(
            build_empty_bollettino_page(cats, base), encoding="utf-8"
        )

    # pagina colonnine ricarica
    tariffe = load_tariffe()
    rdir = OUTPUT_DIR / "ricarica"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "index.html").write_text(
        build_ricarica_page(tariffe, cats, base), encoding="utf-8"
    )

    # feed RSS
    (OUTPUT_DIR / "feed.xml").write_text(build_feed(articles), encoding="utf-8")

    print(
        f"Generati {len(articles)} articoli, {len(cats)} categorie, "
        f"{len(bollettini)} bollettini, 2 pagine informative, pagina colonnine "
        f"({len(tariffe.get('gestori', []))} gestori) e il feed RSS in {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()

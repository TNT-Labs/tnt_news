#!/usr/bin/env python3
"""Generatore del sito statico TNT News.

Legge gli articoli da content/articles/<slug>/ (meta.json + body.html)
e produce il sito statico in docs/ pronto per GitHub Pages.

Nessuna dipendenza esterna: solo libreria standard di Python 3.
"""

import json
import re
import shutil
import unicodedata
from datetime import date, datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content" / "articles"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "docs"

SITE_NAME = "TNT News"
SITE_DESC = "Cronaca e fatti dalla Lombardia e dalla provincia di Bergamo"
SITE_URL = "https://tnt-labs.github.io/tnt_news"
OG_IMAGE = f"{SITE_URL}/og-default.svg"
# Recapito per rettifiche, privacy e segnalazioni. Da personalizzare.
CONTACT = "[inserisci qui l'email di contatto del titolare]"

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
        articles.append(meta)
    # piu recenti in cima
    articles.sort(key=lambda a: a["date"], reverse=True)
    return articles


def all_tags_of(articles: list[dict]) -> list[str]:
    return sorted({t for a in articles for t in a["tags"]})


def render_tags(tags: list[str]) -> str:
    """Tag non cliccabili (usati dentro le card, che sono gia un link)."""
    if not tags:
        return ""
    chips = "".join(f'<span class="tag">{escape(t)}</span>' for t in tags)
    return f'<div class="tags">{chips}</div>'


def render_tag_links(tags: list[str], prefix: str) -> str:
    """Tag cliccabili che portano alla pagina di categoria."""
    if not tags:
        return ""
    chips = "".join(
        f'<a class="tag" href="{prefix}categorie/{slugify(t)}/">{escape(t)}</a>'
        for t in tags
    )
    return f'<div class="tags">{chips}</div>'


def render_categories_nav(tags: list[str], prefix: str) -> str:
    if not tags:
        return ""
    links = "".join(
        f'<a href="{prefix}categorie/{slugify(t)}/">{escape(t)}</a>' for t in tags
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
        " ".join([a["title"], a["summary"], " ".join(a["tags"])]).lower()
    )
    data_tags = escape("|".join(a["tags"]))
    return (
        f'<article class="{cls}" data-search="{blob}" data-tags="{data_tags}">'
        f'<a class="card-link" href="{escape(url)}">'
        f'<div class="card-body">'
        f'{render_tags(a["tags"])}'
        f'<h2 class="card-title">{escape(a["title"])}</h2>'
        f'<p class="card-summary">{escape(a["summary"])}</p>'
        f'<p class="card-meta">{format_date_it(a["date"])}</p>'
        f"</div></a></article>"
    )


def related_articles(article: dict, articles: list[dict], limit: int = 3) -> list[dict]:
    tagset = set(article["tags"])
    others = [a for a in articles if a["slug"] != article["slug"]]
    others.sort(
        key=lambda a: (len(tagset & set(a["tags"])), a["date"]), reverse=True
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


def build_article_page(article: dict, articles: list[dict], all_tags: list[str], base: str) -> str:
    prefix = "../../"
    article_tpl = load_template("article.html")
    content = render(
        article_tpl,
        TITLE=escape(article["title"]),
        DATE_HUMAN=format_date_it(article["date"]),
        DATE_ISO=escape(article["date"]),
        AUTHOR=escape(article["author"]),
        TAGS=render_tag_links(article["tags"], prefix),
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
        categories=render_categories_nav(all_tags, prefix),
        content=content,
    )


def build_category_page(tag: str, articles: list[dict], all_tags: list[str], base: str) -> str:
    prefix = "../../"
    items = [a for a in articles if tag in a["tags"]]
    cards = "".join(render_card(a, prefix) for a in items)
    content = (
        f'<a class="back-link" href="{prefix}index.html">&larr; Tutte le notizie</a>'
        f'<section class="hero-intro"><h1>Categoria: {escape(tag)}</h1>'
        f"<p>{count_phrase(len(items))} in questa categoria.</p></section>"
        f'<div class="card-grid">{cards}</div>'
    )
    return page(
        base,
        title=f"{escape(tag)} — {SITE_NAME}",
        description=escape(f"Notizie nella categoria {tag} su {SITE_NAME}"),
        root=prefix,
        canonical=f"{SITE_URL}/categorie/{slugify(tag)}/",
        og_type="website",
        categories=render_categories_nav(all_tags, prefix),
        content=content,
    )


def build_index_page(articles: list[dict], all_tags: list[str], base: str) -> str:
    index_tpl = load_template("index.html")
    if not articles:
        content = render(
            index_tpl,
            TAGFILTERS="",
            CARDS='<p class="empty">Nessun articolo ancora pubblicato.</p>',
        )
    else:
        filters = [
            '<button type="button" class="tag-filter is-active" data-tag="all">Tutte</button>'
        ]
        for t in all_tags:
            filters.append(
                f'<button type="button" class="tag-filter" data-tag="{escape(t)}">{escape(t)}</button>'
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
        categories=render_categories_nav(all_tags, ""),
        content=content,
    )


def build_simple_page(slug: str, title: str, body: str, all_tags: list[str], base: str) -> str:
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
        categories=render_categories_nav(all_tags, prefix),
        content=content,
    )


def build_feed(articles: list[dict]) -> str:
    items = []
    for a in articles:
        link = f"{SITE_URL}/articoli/{a['slug']}/"
        try:
            d = datetime.strptime(a["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            d = datetime.now(timezone.utc)
        items.append(
            "<item>"
            f"<title>{escape(a['title'])}</title>"
            f"<link>{escape(link)}</link>"
            f'<guid isPermaLink="true">{escape(link)}</guid>'
            f"<pubDate>{format_datetime(d)}</pubDate>"
            f"<description>{escape(a['summary'])}</description>"
            "</item>"
        )
    now = format_datetime(datetime.now(timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{escape(SITE_NAME)}</title>"
        f"<link>{SITE_URL}/</link>"
        f"<description>{escape(SITE_DESC)}</description>"
        "<language>it-it</language>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        f'<atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>'
        + "".join(items)
        + "</channel></rss>\n"
    )


def about_body() -> str:
    return (
        '<article class="article">'
        '<header class="article-header"><h1>Chi siamo</h1>'
        '<p class="article-summary">TNT News è una testata sperimentale a redazione '
        "automatica dedicata alla Lombardia e alla provincia di Bergamo.</p></header>"
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
        "<p>TNT News è una testata sperimentale i cui articoli sono generati "
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


def main() -> None:
    base = load_template("base.html")
    articles = load_articles()
    all_tags = all_tags_of(articles)

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
        build_index_page(articles, all_tags, base), encoding="utf-8"
    )

    # pagine articolo
    for a in articles:
        dest = OUTPUT_DIR / "articoli" / a["slug"]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(
            build_article_page(a, articles, all_tags, base), encoding="utf-8"
        )

    # pagine categoria
    for t in all_tags:
        dest = OUTPUT_DIR / "categorie" / slugify(t)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(
            build_category_page(t, articles, all_tags, base), encoding="utf-8"
        )

    # pagine informative
    for slug, title, body in [
        ("chi-siamo", "Chi siamo", about_body()),
        ("note-legali", "Note legali e privacy", legal_body()),
    ]:
        dest = OUTPUT_DIR / slug
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(
            build_simple_page(slug, title, body, all_tags, base), encoding="utf-8"
        )

    # feed RSS
    (OUTPUT_DIR / "feed.xml").write_text(build_feed(articles), encoding="utf-8")

    print(
        f"Generati {len(articles)} articoli, {len(all_tags)} categorie, "
        f"2 pagine informative e il feed RSS in {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generatore del sito statico TNT News.

Legge gli articoli da content/articles/<slug>/ (meta.json + body.html)
e produce il sito statico in docs/ pronto per GitHub Pages.

Nessuna dipendenza esterna: solo libreria standard di Python 3.
"""

import json
import shutil
from datetime import date, datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content" / "articles"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "docs"

SITE_NAME = "TNT News"
SITE_DESC = "Cronaca e fatti dalla Lombardia e dalla provincia di Bergamo"

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


def render_tags(tags: list[str]) -> str:
    if not tags:
        return ""
    chips = "".join(f'<span class="tag">{escape(t)}</span>' for t in tags)
    return f'<div class="tags">{chips}</div>'


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


def build_article_page(article: dict, base: str) -> str:
    article_tpl = load_template("article.html")
    content = render(
        article_tpl,
        TITLE=escape(article["title"]),
        DATE_HUMAN=format_date_it(article["date"]),
        DATE_ISO=escape(article["date"]),
        AUTHOR=escape(article["author"]),
        TAGS=render_tags(article["tags"]),
        SUMMARY=escape(article["summary"]),
        BODY=article["body"],
        SOURCES=render_sources(article["sources"]),
    )
    return render(
        base,
        TITLE=escape(article["title"]) + " — " + SITE_NAME,
        DESCRIPTION=escape(article["summary"] or SITE_DESC),
        ROOT="../../",
        CONTENT=content,
    )


def build_index_page(articles: list[dict], base: str) -> str:
    index_tpl = load_template("index.html")
    if not articles:
        content = render(
            index_tpl,
            TAGFILTERS="",
            CARDS='<p class="empty">Nessun articolo ancora pubblicato.</p>',
        )
    else:
        all_tags = sorted({t for a in articles for t in a["tags"]})
        filters = [
            '<button type="button" class="tag-filter is-active" data-tag="all">Tutte</button>'
        ]
        for t in all_tags:
            filters.append(
                f'<button type="button" class="tag-filter" data-tag="{escape(t)}">{escape(t)}</button>'
            )
        tagfilters = "".join(filters)

        cards_html = []
        for i, a in enumerate(articles):
            url = f"articoli/{a['slug']}/"
            featured = " featured" if i == 0 else ""
            blob = escape(
                " ".join([a["title"], a["summary"], " ".join(a["tags"])]).lower()
            )
            data_tags = escape("|".join(a["tags"]))
            cards_html.append(
                f'<article class="card{featured}" data-search="{blob}" data-tags="{data_tags}">'
                f'<a class="card-link" href="{escape(url)}">'
                f'<div class="card-body">'
                f'{render_tags(a["tags"])}'
                f'<h2 class="card-title">{escape(a["title"])}</h2>'
                f'<p class="card-summary">{escape(a["summary"])}</p>'
                f'<p class="card-meta">{format_date_it(a["date"])}</p>'
                f"</div></a></article>"
            )
        cards = '<div class="card-grid" id="cardGrid">' + "".join(cards_html) + "</div>"
        content = render(index_tpl, TAGFILTERS=tagfilters, CARDS=cards)
    return render(
        base,
        TITLE=SITE_NAME + " — " + SITE_DESC,
        DESCRIPTION=escape(SITE_DESC),
        ROOT="",
        CONTENT=content,
    )


def main() -> None:
    base = load_template("base.html")
    articles = load_articles()

    # pulizia output mantenendo .git non necessaria (docs e dedicata)
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
        build_index_page(articles, base), encoding="utf-8"
    )

    # pagine articolo
    for a in articles:
        dest = OUTPUT_DIR / "articoli" / a["slug"]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(
            build_article_page(a, base), encoding="utf-8"
        )

    print(f"Generati {len(articles)} articoli in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

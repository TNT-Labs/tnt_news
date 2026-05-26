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
    return render(
        base,
        TITLE=escape(article["title"]) + " — " + SITE_NAME,
        DESCRIPTION=escape(article["summary"] or SITE_DESC),
        ROOT=prefix,
        CATEGORIES=render_categories_nav(all_tags, prefix),
        CONTENT=content,
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
    return render(
        base,
        TITLE=f"{tag} — {SITE_NAME}",
        DESCRIPTION=escape(f"Notizie nella categoria {tag} su {SITE_NAME}"),
        ROOT=prefix,
        CATEGORIES=render_categories_nav(all_tags, prefix),
        CONTENT=content,
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
    return render(
        base,
        TITLE=SITE_NAME + " — " + SITE_DESC,
        DESCRIPTION=escape(SITE_DESC),
        ROOT="",
        CATEGORIES=render_categories_nav(all_tags, ""),
        CONTENT=content,
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

    print(
        f"Generati {len(articles)} articoli e {len(all_tags)} categorie in {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()

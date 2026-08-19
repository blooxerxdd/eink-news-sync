import re
from datetime import date
from html import escape as html_escape
from pathlib import Path

from ebooklib import epub

from article_groups import group_articles_by_section
from htmlutil import sanitize_html, text_to_html_paragraphs
from sources.base import Article

CSS = """
body { font-family: Georgia, serif; line-height: 1.45; margin: 1em; }
h1 { font-size: 1.4em; margin-bottom: 0.3em; }
h2 { font-size: 1.15em; }
.meta { font-size: 0.85em; color: #333; margin-bottom: 1em; }
.trail { font-style: italic; margin-bottom: 1em; }
.section-break { margin-top: 2em; }
a { text-decoration: underline; }
"""

# digest-YYYY-MM-DD.epub (legacy) or digest-YYYY-MM-DD-{source}.epub
DIGEST_FILENAME = re.compile(
    r"^digest-(\d{4}-\d{2}-\d{2})(?:-([a-z0-9][a-z0-9_-]*))?\.epub$"
)


def slug_source_id(source_id: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", source_id.lower()).strip("-_")
    return slug or "source"


def parse_digest_filename(name: str) -> tuple[str, str] | None:
    """Return (date_iso, source_id). source_id is empty for legacy date-only names."""
    match = DIGEST_FILENAME.match(name)
    if not match:
        return None
    return match.group(1), match.group(2) or ""


def digest_filename(digest_date: date, source_id: str) -> str:
    return f"digest-{digest_date.isoformat()}-{slug_source_id(source_id)}.epub"


def build_digest(
    articles: list[Article],
    *,
    output_dir: Path,
    source_name: str,
    source_id: str,
    digest_date: date | None = None,
    groups: list[tuple[str, list[Article]]] | None = None,
) -> Path:
    digest_date = digest_date or date.today()
    slug = slug_source_id(source_id)
    filename = digest_filename(digest_date, slug)
    output_path = output_dir / filename
    groups = groups if groups is not None else group_articles_by_section(articles)
    article_count = sum(len(chunk) for _, chunk in groups)

    book = epub.EpubBook()
    book.set_identifier(f"eink-news-sync-{digest_date.isoformat()}-{slug}")
    book.set_title(f"{source_name} — {digest_date.isoformat()}")
    book.set_language("en")
    book.add_author(source_name)

    style = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=CSS,
    )
    book.add_item(style)

    title_page = epub.EpubHtml(title="Title", file_name="title.xhtml", lang="en")
    title_page.add_item(style)
    title_bits = [
        f"<h1>{html_escape(source_name)}</h1>",
        f'<p class="meta">{html_escape(digest_date.strftime("%A %d %B %Y"))}</p>',
        f'<p class="meta">{article_count} article{"s" if article_count != 1 else ""}</p>',
    ]
    labeled = [(label, chunk) for label, chunk in groups if label]
    if labeled:
        breakdown = "<br/>".join(
            f"{html_escape(label)} — {len(chunk)}" for label, chunk in labeled
        )
        title_bits.append(f'<p class="meta">{breakdown}</p>')
    title_page.content = "\n".join(title_bits)
    book.add_item(title_page)

    spine: list[epub.EpubHtml] = [title_page]
    toc: list = [epub.Link("title.xhtml", "Title page", "title")]
    used_slugs: set[str] = {"title"}
    chapter_index = 0

    for label, chunk in groups:
        section_chapters: list[epub.EpubHtml] = []
        divider = None
        if label:
            sec_slug = _unique_slug(label, used_slugs)
            divider = epub.EpubHtml(
                title=label,
                file_name=f"section_{sec_slug}.xhtml",
                lang="en",
            )
            divider.add_item(style)
            divider.content = f'<div class="section-break"><h1>{html_escape(label)}</h1></div>'
            book.add_item(divider)
            spine.append(divider)

        for article in chunk:
            chapter = epub.EpubHtml(
                title=article.title[:200] or f"Article {chapter_index + 1}",
                file_name=f"chap_{chapter_index:03d}.xhtml",
                lang="en",
            )
            chapter.add_item(style)
            chapter.content = _article_html(article)
            book.add_item(chapter)
            spine.append(chapter)
            section_chapters.append(chapter)
            chapter_index += 1

        if label and divider is not None:
            toc.append(
                (
                    epub.Section(label, divider.file_name),
                    section_chapters,
                )
            )
        else:
            toc.extend(section_chapters)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *spine]
    output_dir.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book)
    return output_path


def _unique_slug(label: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "section"
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def prune_digests(output_dir: Path, retention: int) -> list[str]:
    """Keep the newest `retention` files per source. Returns deleted filenames."""
    groups: dict[str, list[Path]] = {}
    for path in output_dir.glob("digest-*.epub"):
        parsed = parse_digest_filename(path.name)
        if parsed is None:
            continue
        _date, source_id = parsed
        groups.setdefault(source_id, []).append(path)

    deleted: list[str] = []
    keep = max(0, retention)
    for files in groups.values():
        files.sort(key=lambda p: p.name, reverse=True)
        for stale in files[keep:]:
            stale.unlink(missing_ok=True)
            deleted.append(stale.name)
    return deleted


def _article_html(article: Article) -> str:
    parts = [f"<h1>{html_escape(article.title)}</h1>"]
    meta_bits = []
    if article.byline:
        meta_bits.append(html_escape(article.byline))
    if article.section:
        meta_bits.append(html_escape(article.section))
    if article.published_at:
        meta_bits.append(html_escape(article.published_at.strftime("%Y-%m-%d %H:%M UTC")))
    if meta_bits:
        parts.append(f'<p class="meta">{" · ".join(meta_bits)}</p>')
    if article.trail_text:
        parts.append(f'<p class="trail">{html_escape(article.trail_text)}</p>')
    if article.body_html:
        parts.append(sanitize_html(article.body_html))
    else:
        parts.append(text_to_html_paragraphs(article.body_text))
    if article.url:
        parts.append(
            f'<p class="meta"><a href="{html_escape(article.url, quote=True)}">Original article</a></p>'
        )
    return "\n".join(parts)

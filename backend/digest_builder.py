from datetime import date
from html import escape as html_escape
from pathlib import Path

from ebooklib import epub

from htmlutil import sanitize_html, text_to_html_paragraphs
from sources.base import Article

CSS = """
body { font-family: Georgia, serif; line-height: 1.45; margin: 1em; }
h1 { font-size: 1.4em; margin-bottom: 0.3em; }
h2 { font-size: 1.15em; }
.meta { font-size: 0.85em; color: #333; margin-bottom: 1em; }
.trail { font-style: italic; margin-bottom: 1em; }
a { text-decoration: underline; }
"""


def build_digest(
    articles: list[Article],
    *,
    output_dir: Path,
    source_name: str,
    digest_date: date | None = None,
) -> Path:
    digest_date = digest_date or date.today()
    filename = f"digest-{digest_date.isoformat()}.epub"
    output_path = output_dir / filename

    book = epub.EpubBook()
    book.set_identifier(f"eink-news-sync-{digest_date.isoformat()}")
    book.set_title(f"Daily Digest — {digest_date.isoformat()}")
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
    title_page.content = f"""
      <h1>Daily Digest</h1>
      <p class="meta">{html_escape(digest_date.strftime("%A %d %B %Y"))}</p>
      <p class="meta">{html_escape(source_name)} · {len(articles)} article{"s" if len(articles) != 1 else ""}</p>
    """
    book.add_item(title_page)

    chapters: list[epub.EpubHtml] = []
    for index, article in enumerate(articles):
        chapter = epub.EpubHtml(
            title=article.title[:200] or f"Article {index + 1}",
            file_name=f"chap_{index:03d}.xhtml",
            lang="en",
        )
        chapter.add_item(style)
        chapter.content = _article_html(article)
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = [
        epub.Link("title.xhtml", "Title page", "title"),
        *[epub.Link(ch.file_name, ch.title, f"chap{i}") for i, ch in enumerate(chapters)],
    ]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", title_page, *chapters]
    output_dir.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book)
    return output_path


def prune_digests(output_dir: Path, retention: int) -> list[str]:
    """Keep the newest `retention` digest-*.epub files. Returns deleted filenames."""
    files = sorted(
        output_dir.glob("digest-*.epub"),
        key=lambda p: p.name,
        reverse=True,
    )
    deleted: list[str] = []
    for stale in files[max(0, retention) :]:
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

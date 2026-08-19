from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
import trafilatura

from htmlutil import sanitize_html
from sources.base import Article, ArticleStub, ConfigField, NewsSource

DEFAULT_BASE_URL = "https://blog.arjaythedev.com"
POSTS_PER_PAGE = 50
MAX_PAGES = 200
USER_AGENT = "eink-news-sync/0.1 (+https://github.com/eink-news-sync)"


class ArjayBlogSource(NewsSource):
    source_id = "arjay_blog"
    display_name = "The Dev Download"
    digest_mode = "archive"
    output_filename = "arjay-blog-archive.epub"
    ignores_max_items = True
    description = (
        "Archives every public post from blog.arjaythedev.com into one EPUB "
        "(arjay-blog-archive.epub). The site URL is built in — you only choose "
        "reading order, then include the source in sync."
    )

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="chapter_order",
                label="Reading order",
                type="select",
                required=False,
                default="oldest",
                options=[
                    {
                        "value": "oldest",
                        "label": "Oldest first — earliest post at the start of the book",
                    },
                    {
                        "value": "newest",
                        "label": "Newest first — latest post at the start of the book",
                    },
                ],
                help="Oldest first is usually better for a blog archive: you read in the order the posts were written.",
            ),
        ]

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        order = str(config.get("chapter_order") or "oldest").strip()
        if order not in {"oldest", "newest"}:
            problems.append("Reading order must be oldest or newest.")
        return problems

    async def get_headlines(
        self,
        config: dict[str, Any],
        max_items: int,
        *,
        known_ok_ids: set[str] | None = None,
    ) -> list[ArticleStub]:
        known = known_ok_ids or set()
        base = _base_url(config)
        stubs: list[ArticleStub] = []
        page = 1

        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": USER_AGENT}) as client:
            while page <= MAX_PAGES:
                response = await client.get(
                    f"{base}/posts",
                    params={"page": page, "per_page": POSTS_PER_PAGE},
                )
                response.raise_for_status()
                payload = response.json()
                posts = payload.get("posts") or []
                if not posts:
                    break

                hit_known = False
                for item in posts:
                    stub = item_to_stub(item, base)
                    if stub.external_id in known:
                        hit_known = True
                        break
                    stubs.append(stub)

                if hit_known:
                    break
                pagination = payload.get("pagination") or {}
                try:
                    total_pages = int(pagination.get("total_pages") or page)
                except (TypeError, ValueError):
                    total_pages = page
                if page >= total_pages:
                    break
                page += 1

        return stubs

    async def fetch_article(self, config: dict[str, Any], stub: ArticleStub) -> Article | None:
        if stub.body_text or stub.body_html:
            return self.stub_to_article(stub)
        try:
            async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(stub.url)
                if response.status_code in {401, 403, 404}:
                    return None
                response.raise_for_status()
                html = response.text
        except httpx.HTTPError:
            return None

        body_text = trafilatura.extract(html, include_comments=False, include_tables=False)
        body_html = trafilatura.extract(
            html,
            output_format="html",
            include_comments=False,
            include_tables=False,
        )
        if body_html:
            body_html = sanitize_html(body_html)
        if not body_text and not body_html:
            return None

        published = stub.published_at or _trafilatura_date(html)
        word_count = len(body_text.split()) if body_text else None
        stub.body_text = body_text
        stub.body_html = body_html
        stub.published_at = published
        stub.word_count = word_count
        return self.stub_to_article(stub)

    def organize_digest(
        self, articles: list[Article], config: dict[str, Any] | None = None
    ) -> list[tuple[str, list[Article]]]:
        order = str((config or {}).get("chapter_order") or "oldest").strip() or "oldest"
        newest_first = order == "newest"

        def sort_key(article: Article) -> tuple[float, str]:
            stamp = article.published_at.timestamp() if article.published_at else 0.0
            if newest_first:
                stamp = -stamp
            return (stamp, article.title.casefold())

        return [("", sorted(articles, key=sort_key))]


def item_to_stub(item: dict[str, Any], base_url: str) -> ArticleStub:
    slug = str(item.get("slug") or "").strip()
    url = urljoin(base_url.rstrip("/") + "/", f"p/{slug}") if slug else base_url
    authors = item.get("authors") or []
    byline = None
    if isinstance(authors, list) and authors:
        name = authors[0].get("name") if isinstance(authors[0], dict) else None
        byline = str(name).strip() if name else None
    subtitle = item.get("web_subtitle")
    trail = str(subtitle).strip() if subtitle else None
    return ArticleStub(
        source_id="arjay_blog",
        external_id=url,
        title=str(item.get("web_title") or "Untitled"),
        url=url,
        published_at=_parse_dt(item.get("override_scheduled_at") or item.get("created_at")),
        byline=byline,
        trail_text=trail or None,
    )


def _base_url(_config: dict[str, Any] | None = None) -> str:
    return DEFAULT_BASE_URL.rstrip("/")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _trafilatura_date(html: str) -> datetime | None:
    try:
        meta = trafilatura.extract_metadata(html)
    except Exception:
        return None
    if meta is None or not getattr(meta, "date", None):
        return None
    return _parse_dt(str(meta.date))

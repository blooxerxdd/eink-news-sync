from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from htmlutil import html_to_text
from sources.base import Article, ArticleStub, ConfigField, NewsSource

GUARDIAN_SEARCH = "https://content.guardianapis.com/search"
PAGE_SIZE_CAP = 50


class GuardianSource(NewsSource):
    source_id = "guardian"
    display_name = "The Guardian"

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="api_key",
                label="API key",
                type="secret",
                required=True,
                help="Free key from https://open-platform.theguardian.com/access/",
            ),
            ConfigField(
                key="sections",
                label="Sections",
                type="tags",
                required=False,
                default=[],
                help="Guardian section IDs, e.g. world, uk-news, us-news, business, technology, science. Leave empty for all sections.",
            ),
            ConfigField(
                key="lookback_hours",
                label="Lookback (hours)",
                type="number",
                required=False,
                default=24,
                help="Only include articles published within this window.",
            ),
        ]

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            problems.append("API key is required.")

        sections = config.get("sections", [])
        if sections is None:
            sections = []
        if isinstance(sections, str):
            sections = [s.strip() for s in sections.split(",") if s.strip()]
        if not isinstance(sections, list) or any(not isinstance(s, str) or not s.strip() for s in sections):
            problems.append("Sections must be a list of section IDs (e.g. world, business).")

        lookback = config.get("lookback_hours", 24)
        try:
            hours = int(lookback)
            if hours <= 0 or hours > 24 * 14:
                problems.append("Lookback hours must be between 1 and 336 (14 days).")
        except (TypeError, ValueError):
            problems.append("Lookback hours must be a number.")

        return problems

    async def get_headlines(self, config: dict[str, Any], max_items: int) -> list[ArticleStub]:
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("Guardian API key is not configured.")

        lookback_hours = int(config.get("lookback_hours") or 24)
        sections = _normalize_sections(config.get("sections"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        from_date = cutoff.date().isoformat()

        wanted = max(1, min(int(max_items), 200))
        stubs: list[ArticleStub] = []
        page = 1

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(stubs) < wanted:
                page_size = min(PAGE_SIZE_CAP, wanted - len(stubs))
                params: dict[str, str | int] = {
                    "api-key": api_key,
                    "order-by": "newest",
                    "page-size": page_size,
                    "page": page,
                    "from-date": from_date,
                    "type": "article",
                    "show-fields": "body,byline,trailText,wordcount",
                }
                if sections:
                    params["section"] = "|".join(sections)

                response = await client.get(GUARDIAN_SEARCH, params=params)
                if response.status_code == 401:
                    raise ValueError("Guardian API key was rejected (401).")
                if response.status_code == 403:
                    raise ValueError("Guardian API key was rejected (403).")
                if response.status_code == 429:
                    raise ValueError("Guardian API rate limit exceeded. Try again later.")
                response.raise_for_status()
                payload = response.json().get("response", {})
                results = payload.get("results") or []
                if not results:
                    break

                for item in results:
                    stub = _item_to_stub(item)
                    if stub.published_at and stub.published_at < cutoff:
                        continue
                    stubs.append(stub)
                    if len(stubs) >= wanted:
                        break

                pages = int(payload.get("pages") or page)
                if page >= pages:
                    break
                page += 1

        return stubs[:wanted]

    async def fetch_article(self, config: dict[str, Any], stub: ArticleStub) -> Article | None:
        # Search already requested show-fields=body,... so headlines usually
        # arrive fully populated. Return that copy instead of a second round trip.
        return self.stub_to_article(stub)

    def organize_digest(
        self, articles: list[Article], config: dict[str, Any] | None = None
    ) -> list[tuple[str, list[Article]]]:
        from article_groups import group_articles_by_section

        return group_articles_by_section(
            articles,
            section_order=_normalize_sections((config or {}).get("sections")),
        )


def _normalize_sections(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    return []


def _item_to_stub(item: dict[str, Any]) -> ArticleStub:
    fields = item.get("fields") or {}
    body_html = fields.get("body") or None
    trail = fields.get("trailText") or None
    byline = fields.get("byline") or None
    word_count_raw = fields.get("wordcount")
    try:
        word_count = int(word_count_raw) if word_count_raw else None
    except (TypeError, ValueError):
        word_count = None

    published_at = _parse_dt(item.get("webPublicationDate"))
    body_text = html_to_text(body_html) if body_html else ""

    section_id = item.get("sectionId")
    section_id = str(section_id).strip() if section_id else None
    section_name = item.get("sectionName")
    section_name = str(section_name).strip() if section_name else None

    return ArticleStub(
        source_id="guardian",
        external_id=str(item.get("id") or item.get("webUrl") or ""),
        title=str(item.get("webTitle") or "Untitled"),
        url=str(item.get("webUrl") or ""),
        section=section_name or section_id,
        published_at=published_at,
        byline=byline,
        body_text=body_text or None,
        body_html=body_html,
        trail_text=html_to_text(trail) if trail else None,
        word_count=word_count or (len(body_text.split()) if body_text else None),
        section_id=section_id,
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

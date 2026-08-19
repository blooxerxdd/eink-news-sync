from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class ArticleStub:
    source_id: str
    external_id: str
    title: str
    url: str
    section: str | None = None
    published_at: datetime | None = None
    byline: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    trail_text: str | None = None
    word_count: int | None = None
    section_id: str | None = None


@dataclass
class Article:
    source_id: str
    external_id: str
    title: str
    url: str
    section: str | None
    published_at: datetime
    byline: str | None
    body_text: str
    body_html: str | None
    trail_text: str | None = None
    word_count: int | None = None
    section_id: str | None = None


@dataclass
class ConfigField:
    key: str
    label: str
    type: str  # "secret" | "text" | "number" | "tags"
    required: bool = False
    default: Any = None
    help: str | None = None


class NewsSource(ABC):
    source_id: str
    display_name: str

    @abstractmethod
    async def get_headlines(self, config: dict[str, Any], max_items: int) -> list[ArticleStub]:
        """Cheap call: candidate articles. May pre-populate body if the source returned it."""

    @abstractmethod
    async def fetch_article(self, config: dict[str, Any], stub: ArticleStub) -> Article | None:
        """Full article body. Returns None if unavailable/paywalled/failed.

        If get_headlines already attached a body, return that cached copy.
        """

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Human-readable config problems; empty if OK."""

    @abstractmethod
    def config_fields(self) -> list[ConfigField]:
        """Generic form schema so the UI does not hardcode per-source fields."""

    def stub_to_article(self, stub: ArticleStub) -> Article | None:
        if not stub.body_text and not stub.body_html:
            return None
        published = stub.published_at or datetime.now(timezone.utc)
        body_text = stub.body_text or ""
        return Article(
            source_id=stub.source_id,
            external_id=stub.external_id,
            title=stub.title,
            url=stub.url,
            section=stub.section,
            published_at=published,
            byline=stub.byline,
            body_text=body_text,
            body_html=stub.body_html,
            trail_text=stub.trail_text,
            word_count=stub.word_count or (len(body_text.split()) if body_text else None),
            section_id=stub.section_id,
        )

    def organize_digest(
        self, articles: list[Article], config: dict[str, Any] | None = None
    ) -> list[tuple[str, list[Article]]]:
        """Group articles for one EPUB. Override to apply source-specific section order."""
        from article_groups import group_articles_by_section

        return group_articles_by_section(articles)

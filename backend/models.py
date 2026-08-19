"""SQLite schema via SQLModel.

v1 uses SQLModel.metadata.create_all() on startup. Introduce Alembic if/when
the schema needs to change after real digests have accumulated.
"""

from datetime import datetime, timezone

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceConfig(SQLModel, table=True):
    __tablename__ = "sources_config"

    id: int | None = Field(default=None, primary_key=True)
    source_id: str = Field(index=True, unique=True)
    is_active: bool = Field(default=False)
    config_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: datetime | None = None
    status: str = Field(default="running", index=True)
    source_id: str
    articles_fetched: int = Field(default=0)
    articles_failed: int = Field(default=0)
    error_message: str | None = None
    digest_filename: str | None = None
    articles: list["ArticleRecord"] = Relationship(back_populates="run")


class ArticleRecord(SQLModel, table=True):
    """Persisted fetch metadata for the history UI. Full body is not stored."""

    __tablename__ = "articles"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    source_id: str
    external_id: str
    title: str
    url: str
    section: str | None = None
    published_at: datetime | None = None
    byline: str | None = None
    fetch_status: str
    word_count: int | None = None
    run: Run | None = Relationship(back_populates="articles")


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)
    value: str


class AccessEvent(SQLModel, table=True):
    """OPDS/download hits from LAN clients (e-reader, etc.)."""

    __tablename__ = "access_events"

    id: int | None = Field(default=None, primary_key=True)
    seen_at: datetime = Field(default_factory=utcnow, index=True)
    client_ip: str = Field(index=True)
    user_agent: str | None = None
    method: str
    path: str
    status_code: int

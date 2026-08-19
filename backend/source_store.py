from datetime import datetime, timezone

from sqlmodel import Session, select

from models import SourcePost, utcnow
from sources.base import Article, ArticleStub


def load_ok_ids(session: Session, source_id: str) -> set[str]:
    rows = session.exec(
        select(SourcePost.external_id).where(
            SourcePost.source_id == source_id,
            SourcePost.fetch_status == "ok",
        )
    ).all()
    return set(rows)


def load_ok_articles(session: Session, source_id: str) -> list[Article]:
    rows = session.exec(
        select(SourcePost).where(
            SourcePost.source_id == source_id,
            SourcePost.fetch_status == "ok",
        )
    ).all()
    articles: list[Article] = []
    for row in rows:
        article = _row_to_article(row)
        if article is not None:
            articles.append(article)
    return articles


def upsert_article(session: Session, article: Article) -> None:
    _upsert(
        session,
        source_id=article.source_id,
        external_id=article.external_id,
        title=article.title,
        url=article.url,
        section=article.section,
        published_at=article.published_at,
        byline=article.byline,
        body_text=article.body_text,
        body_html=article.body_html,
        trail_text=article.trail_text,
        fetch_status="ok",
        word_count=article.word_count,
    )


def upsert_failed(session: Session, stub: ArticleStub, fetch_status: str) -> None:
    _upsert(
        session,
        source_id=stub.source_id,
        external_id=stub.external_id,
        title=stub.title,
        url=stub.url,
        section=stub.section,
        published_at=stub.published_at,
        byline=stub.byline,
        body_text=stub.body_text or "",
        body_html=stub.body_html,
        trail_text=stub.trail_text,
        fetch_status=fetch_status,
        word_count=stub.word_count,
    )


def _upsert(
    session: Session,
    *,
    source_id: str,
    external_id: str,
    title: str,
    url: str,
    section: str | None,
    published_at: datetime | None,
    byline: str | None,
    body_text: str,
    body_html: str | None,
    trail_text: str | None,
    fetch_status: str,
    word_count: int | None,
) -> None:
    existing = session.exec(
        select(SourcePost).where(
            SourcePost.source_id == source_id,
            SourcePost.external_id == external_id,
        )
    ).first()
    if existing is None:
        session.add(
            SourcePost(
                source_id=source_id,
                external_id=external_id,
                title=title,
                url=url,
                section=section,
                published_at=published_at,
                byline=byline,
                body_text=body_text,
                body_html=body_html,
                trail_text=trail_text,
                fetch_status=fetch_status,
                word_count=word_count,
                updated_at=utcnow(),
            )
        )
        return
    existing.title = title
    existing.url = url
    existing.section = section
    existing.published_at = published_at
    existing.byline = byline
    existing.body_text = body_text
    existing.body_html = body_html
    existing.trail_text = trail_text
    existing.fetch_status = fetch_status
    existing.word_count = word_count
    existing.updated_at = utcnow()
    session.add(existing)


def _row_to_article(row: SourcePost) -> Article | None:
    if not row.body_text and not row.body_html:
        return None
    published = row.published_at or datetime.now(timezone.utc)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return Article(
        source_id=row.source_id,
        external_id=row.external_id,
        title=row.title,
        url=row.url,
        section=row.section,
        published_at=published,
        byline=row.byline,
        body_text=row.body_text or "",
        body_html=row.body_html,
        trail_text=row.trail_text,
        word_count=row.word_count,
    )

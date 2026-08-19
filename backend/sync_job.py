import logging

from sqlmodel import Session, select

from config import DIGESTS_DIR
from database import engine, get_settings_map
from digest_builder import build_digest, prune_digests
from models import ArticleRecord, Run, SourceConfig, utcnow
from sources import get_source
from sources.base import Article
from util import load_json

logger = logging.getLogger("eink-news-sync")


async def execute_run(run_id: int) -> None:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            logger.error("Run %s disappeared before execution", run_id)
            return
        source_row = session.exec(
            select(SourceConfig).where(SourceConfig.source_id == run.source_id)
        ).first()
        settings = get_settings_map(session)
        if source_row is None:
            _fail(session, run, f"Source '{run.source_id}' is not configured.")
            return
        config = load_json(source_row.config_json)
        max_articles = int(settings.get("max_articles") or 20)
        retention = int(settings.get("digest_retention") or 14)

    try:
        source = get_source(run.source_id)
    except KeyError as exc:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run:
                _fail(session, run, str(exc))
        return

    problems = source.validate_config(config)
    if problems:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run:
                _fail(session, run, "; ".join(problems))
        return

    articles: list[Article] = []
    failed = 0
    records: list[ArticleRecord] = []

    try:
        stubs = await source.get_headlines(config, max_articles)
        for stub in stubs:
            article = await source.fetch_article(config, stub)
            if article is None:
                failed += 1
                records.append(
                    ArticleRecord(
                        run_id=run_id,
                        source_id=stub.source_id,
                        external_id=stub.external_id,
                        title=stub.title,
                        url=stub.url,
                        section=stub.section,
                        published_at=stub.published_at,
                        byline=stub.byline,
                        fetch_status="skipped_paywall" if not stub.body_html else "failed",
                        word_count=stub.word_count,
                    )
                )
                continue
            articles.append(article)
            records.append(
                ArticleRecord(
                    run_id=run_id,
                    source_id=article.source_id,
                    external_id=article.external_id,
                    title=article.title,
                    url=article.url,
                    section=article.section,
                    published_at=article.published_at,
                    byline=article.byline,
                    fetch_status="ok",
                    word_count=article.word_count,
                )
            )
    except Exception as exc:
        logger.exception("Source fetch failed")
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run:
                for rec in records:
                    session.add(rec)
                run.articles_fetched = len(articles)
                run.articles_failed = failed
                _fail(session, run, str(exc))
        return

    digest_filename = None
    error_message = None
    if articles:
        try:
            path = build_digest(
                articles,
                output_dir=DIGESTS_DIR,
                source_name=source.display_name,
                source_id=source.source_id,
            )
            digest_filename = path.name
            prune_digests(DIGESTS_DIR, retention)
        except Exception as exc:
            logger.exception("Digest build failed")
            error_message = f"Articles fetched but EPUB build failed: {exc}"
    else:
        error_message = "No articles with usable body text were returned."

    if digest_filename and failed == 0:
        status = "success"
    elif digest_filename:
        status = "partial"
    else:
        status = "error"

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        for rec in records:
            session.add(rec)
        run.articles_fetched = len(articles)
        run.articles_failed = failed
        run.digest_filename = digest_filename
        run.error_message = error_message
        run.status = status
        run.finished_at = utcnow()
        session.add(run)
        session.commit()
        logger.info(
            "Run %s finished status=%s fetched=%s failed=%s digest=%s",
            run_id,
            status,
            len(articles),
            failed,
            digest_filename,
        )


def _fail(session: Session, run: Run, message: str) -> None:
    run.status = "error"
    run.error_message = message
    run.finished_at = utcnow()
    session.add(run)
    session.commit()

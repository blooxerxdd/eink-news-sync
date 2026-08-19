import logging

from sqlmodel import Session, select

from config import DIGESTS_DIR
from database import engine, get_settings_map
from digest_builder import build_digest, prune_digests
from models import ArticleRecord, Run, SourceConfig, utcnow
from source_store import load_ok_articles, load_ok_ids, upsert_article, upsert_failed
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
        known_ok_ids = load_ok_ids(session, run.source_id)

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

    is_archive = source.digest_mode == "archive"
    if source.ignores_max_items:
        max_articles = max(max_articles, 10_000)

    new_articles: list[Article] = []
    failed = 0
    records: list[ArticleRecord] = []
    failed_stubs: list[tuple] = []

    try:
        stubs = await source.get_headlines(config, max_articles, known_ok_ids=known_ok_ids)
        for stub in stubs:
            article = await source.fetch_article(config, stub)
            if article is None:
                failed += 1
                status = "failed" if is_archive else ("skipped_paywall" if not stub.body_html else "failed")
                failed_stubs.append((stub, status))
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
                        fetch_status=status,
                        word_count=stub.word_count,
                    )
                )
                continue
            new_articles.append(article)
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
                _persist_posts(session, new_articles, failed_stubs, is_archive)
                run.articles_fetched = len(new_articles)
                run.articles_failed = failed
                _fail(session, run, str(exc))
        return

    digest_articles = new_articles
    if is_archive:
        with Session(engine) as session:
            _persist_posts(session, new_articles, failed_stubs, True)
            session.commit()
            digest_articles = load_ok_articles(session, source.source_id)

    digest_filename = None
    error_message = None
    if digest_articles:
        try:
            path = build_digest(
                digest_articles,
                output_dir=DIGESTS_DIR,
                source_name=source.display_name,
                source_id=source.source_id,
                groups=source.organize_digest(digest_articles, config),
                filename=source.output_filename,
                persistent=is_archive,
                date_under_title=is_archive,
            )
            digest_filename = path.name
            if not is_archive:
                prune_digests(DIGESTS_DIR, retention)
        except Exception as exc:
            logger.exception("Digest build failed")
            error_message = f"Articles fetched but EPUB build failed: {exc}"
    elif is_archive:
        error_message = None
    else:
        error_message = "No articles with usable body text were returned."

    if is_archive and digest_filename and failed == 0:
        status = "success"
        error_message = None
    elif digest_filename and failed == 0:
        status = "success"
    elif digest_filename:
        status = "partial"
    else:
        status = "error"
        if not error_message:
            error_message = "No articles with usable body text were returned."

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        for rec in records:
            session.add(rec)
        if not is_archive:
            _persist_posts(session, new_articles, failed_stubs, False)
        run.articles_fetched = len(new_articles)
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
            len(new_articles),
            failed,
            digest_filename,
        )


def _persist_posts(session: Session, articles: list[Article], failed_stubs: list, is_archive: bool) -> None:
    if not is_archive:
        return
    for article in articles:
        upsert_article(session, article)
    for stub, status in failed_stubs:
        upsert_failed(session, stub, status)


def _fail(session: Session, run: Run, message: str) -> None:
    run.status = "error"
    run.error_message = message
    run.finished_at = utcnow()
    session.add(run)
    session.commit()

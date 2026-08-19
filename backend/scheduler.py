import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session

from config import TESTING
from database import engine, get_settings_map
from models import Run, utcnow
from sources import SOURCES
from sync_job import execute_run
from util import get_active_source_rows

logger = logging.getLogger("eink-news-sync")

scheduler = AsyncIOScheduler()
_run_lock = asyncio.Lock()
JOB_ID = "daily_sync"


class RunInProgress(Exception):
    pass


def is_run_in_progress() -> bool:
    return _run_lock.locked()


async def trigger_run(*, source_id: str | None = None) -> Run:
    if _run_lock.locked():
        raise RunInProgress("A sync is already in progress")
    await _run_lock.acquire()
    try:
        source_ids = _resolve_source_ids(source_id)
        first = _create_run(source_ids[0])
    except Exception:
        _run_lock.release()
        raise
    asyncio.create_task(_run_wrapper(first.id, source_ids[1:]))
    return first


def start_scheduler() -> None:
    if TESTING:
        return
    if not scheduler.running:
        scheduler.start()
    reschedule_from_db()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def reschedule_from_db() -> None:
    if TESTING or not scheduler.running:
        return
    with Session(engine) as session:
        settings = get_settings_map(session)
    hour = int(settings.get("sync_hour") or 6)
    minute = int(settings.get("sync_minute") or 0)
    trigger = CronTrigger(hour=hour, minute=minute)
    existing = scheduler.get_job(JOB_ID)
    if existing:
        existing.reschedule(trigger=trigger)
    else:
        scheduler.add_job(
            _scheduled_fire,
            trigger=trigger,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    logger.info("Scheduler set for %02d:%02d local time", hour, minute)


def next_run_iso() -> str | None:
    job = scheduler.get_job(JOB_ID) if scheduler.running else None
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()


def _resolve_source_ids(source_id: str | None) -> list[str]:
    if source_id:
        return [source_id]
    with Session(engine) as session:
        rows = get_active_source_rows(session)
    ids = [row.source_id for row in rows if row.source_id in SOURCES]
    return ids or [next(iter(SOURCES))]


def _create_run(source_id: str) -> Run:
    with Session(engine) as session:
        run = Run(started_at=utcnow(), status="running", source_id=source_id)
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


async def _run_wrapper(first_run_id: int, remaining_source_ids: list[str]) -> None:
    try:
        await execute_run(first_run_id)
        for extra_id in remaining_source_ids:
            run = _create_run(extra_id)
            await execute_run(run.id)
    except Exception:
        logger.exception("Unhandled error while building source digests")
    finally:
        if _run_lock.locked():
            _run_lock.release()


async def _scheduled_fire() -> None:
    try:
        await trigger_run()
    except RunInProgress:
        logger.warning("Skipping scheduled sync; a run is already in progress")

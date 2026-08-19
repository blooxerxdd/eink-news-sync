import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from config import ACCESS_EVENT_LIMIT, DEVICE_RECENT_SECONDS
from database import engine
from models import AccessEvent, utcnow

logger = logging.getLogger("eink-news-sync")


def is_device_path(path: str) -> bool:
    return path == "/opds" or path.startswith("/download/")


def record_access(
    *,
    client_ip: str,
    user_agent: str | None,
    method: str,
    path: str,
    status_code: int,
) -> None:
    try:
        with Session(engine) as session:
            session.add(
                AccessEvent(
                    seen_at=utcnow(),
                    client_ip=client_ip[:64],
                    user_agent=(user_agent or "")[:512] or None,
                    method=method[:16],
                    path=path[:512],
                    status_code=status_code,
                )
            )
            session.commit()
            _prune(session)
    except Exception:
        logger.exception("Failed to record device access event")


def _prune(session: Session) -> None:
    count = session.exec(select(func.count()).select_from(AccessEvent)).one()
    extra = int(count) - ACCESS_EVENT_LIMIT
    if extra <= 0:
        return
    stale_ids = session.exec(
        select(AccessEvent.id).order_by(col(AccessEvent.seen_at).asc()).limit(extra)
    ).all()
    for event_id in stale_ids:
        row = session.get(AccessEvent, event_id)
        if row is not None:
            session.delete(row)
    session.commit()


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(
            select(AccessEvent).order_by(col(AccessEvent.seen_at).desc()).limit(limit)
        ).all()
        return [_serialize_event(row) for row in rows]


def list_devices() -> list[dict[str, Any]]:
    cutoff = utcnow() - timedelta(seconds=DEVICE_RECENT_SECONDS)
    with Session(engine) as session:
        rows = session.exec(select(AccessEvent).order_by(col(AccessEvent.seen_at).desc())).all()

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.client_ip, row.user_agent or "")
        bucket = grouped.get(key)
        if bucket is None:
            grouped[key] = {
                "client_ip": row.client_ip,
                "user_agent": row.user_agent,
                "first_seen_at": row.seen_at,
                "last_seen_at": row.seen_at,
                "last_path": row.path,
                "last_status": row.status_code,
                "request_count": 1,
            }
        else:
            bucket["request_count"] += 1
            bucket["first_seen_at"] = min(bucket["first_seen_at"], row.seen_at)
            if row.seen_at > bucket["last_seen_at"]:
                bucket["last_seen_at"] = row.seen_at
                bucket["last_path"] = row.path
                bucket["last_status"] = row.status_code

    devices = []
    for bucket in grouped.values():
        cutoff = utcnow() - timedelta(seconds=DEVICE_RECENT_SECONDS)
        last_seen = _aware(bucket["last_seen_at"])
        first_seen = _aware(bucket["first_seen_at"])
        devices.append(
            {
                "client_ip": bucket["client_ip"],
                "user_agent": bucket["user_agent"],
                "first_seen_at": first_seen.isoformat(),
                "last_seen_at": last_seen.isoformat(),
                "last_path": bucket["last_path"],
                "last_status": bucket["last_status"],
                "request_count": bucket["request_count"],
                "recent": last_seen >= cutoff,
            }
        )
    devices.sort(key=lambda item: item["last_seen_at"], reverse=True)
    return devices


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _serialize_event(row: AccessEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "seen_at": _aware(row.seen_at).isoformat() if row.seen_at else None,
        "client_ip": row.client_ip,
        "user_agent": row.user_agent,
        "method": row.method,
        "path": row.path,
        "status_code": row.status_code,
    }

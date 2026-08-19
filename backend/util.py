import json
import socket
from typing import Any

from sqlmodel import Session, select

from config import SECRET_CONFIG_KEYS
from models import AppSetting, ArticleRecord, Run, SourceConfig, utcnow


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


def looks_masked(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return True
    return "•" in value or value.startswith("****")


def mask_config(config: dict[str, Any]) -> dict[str, Any]:
    masked = dict(config)
    for key in list(masked):
        if key in SECRET_CONFIG_KEYS and isinstance(masked[key], str):
            masked[key] = mask_secret(masked[key])
    return masked


def merge_config(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in SECRET_CONFIG_KEYS and looks_masked(value):
            continue
        merged[key] = value
    return merged


def load_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def get_active_source_row(session: Session) -> SourceConfig | None:
    rows = get_active_source_rows(session)
    return rows[0] if rows else None


def get_active_source_rows(session: Session) -> list[SourceConfig]:
    return list(session.exec(select(SourceConfig).where(SourceConfig.is_active == True)).all())  # noqa: E712


def activate_source(session: Session, source_id: str, *, active: bool = True) -> SourceConfig:
    rows = session.exec(select(SourceConfig)).all()
    target: SourceConfig | None = None
    for row in rows:
        if row.source_id == source_id:
            row.is_active = active
            row.updated_at = utcnow()
            target = row
    if target is None:
        target = SourceConfig(source_id=source_id, is_active=active, config_json="{}")
        session.add(target)
    _sync_active_source_setting(session)
    session.commit()
    session.refresh(target)
    return target


def _sync_active_source_setting(session: Session) -> None:
    actives = [
        row.source_id
        for row in session.exec(select(SourceConfig).where(SourceConfig.is_active == True)).all()  # noqa: E712
    ]
    value = ",".join(actives)
    setting = session.get(AppSetting, "active_source_id")
    if setting:
        setting.value = value
        session.add(setting)
    else:
        session.add(AppSetting(key="active_source_id", value=value))


def serialize_run(run: Run, *, include_articles: bool = False) -> dict[str, Any]:
    duration_s = None
    if run.finished_at and run.started_at:
        duration_s = (run.finished_at - run.started_at).total_seconds()
    payload: dict[str, Any] = {
        "id": run.id,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "status": run.status,
        "source_id": run.source_id,
        "articles_fetched": run.articles_fetched,
        "articles_failed": run.articles_failed,
        "error_message": run.error_message,
        "digest_filename": run.digest_filename,
        "duration_seconds": duration_s,
    }
    if include_articles:
        payload["articles"] = [serialize_article(a) for a in (run.articles or [])]
    return payload


def serialize_article(article: ArticleRecord) -> dict[str, Any]:
    return {
        "id": article.id,
        "source_id": article.source_id,
        "external_id": article.external_id,
        "title": article.title,
        "url": article.url,
        "section": article.section,
        "published_at": _iso(article.published_at),
        "byline": article.byline,
        "fetch_status": article.fetch_status,
        "word_count": article.word_count,
    }


def primary_lan_ipv4() -> str | None:
    """Best-effort IPv4 that other devices on the LAN should use to reach this host."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("1.1.1.1", 80))
        ip = sock.getsockname()[0]
        sock.close()
    except OSError:
        return None
    if not ip or ip.startswith("127."):
        return None
    return ip


def lan_ipv4_addresses() -> list[str]:
    found: list[str] = []
    primary = primary_lan_ipv4()
    if primary:
        found.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

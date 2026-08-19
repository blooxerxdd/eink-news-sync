from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from access_log import is_device_path, list_devices, list_events, record_access

from config import DIGESTS_DIR, PORT, TESTING
from database import get_session, get_settings_map, init_db
from models import ArticleRecord, Run, SourceConfig, utcnow
from opds import build_opds_feed, list_digest_files
from scheduler import (
    RunInProgress,
    is_run_in_progress,
    next_run_iso,
    reschedule_from_db,
    shutdown_scheduler,
    start_scheduler,
    trigger_run,
)
from sources import SOURCES, get_source
from util import (
    activate_source,
    get_active_source_row,
    lan_ipv4_addresses,
    load_json,
    mask_config,
    merge_config,
    primary_lan_ipv4,
    serialize_article,
    serialize_run,
)

logging.basicConfig(level=logging.INFO)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
SAFE_DIGEST = re.compile(r"^digest-\d{4}-\d{2}-\d{2}\.epub$")

LAN_WARNING = "LAN-only. Do not port-forward or expose this service to the internet."


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="eink-news-sync",
    version="0.1.0",
    description=f"Daily news digest builder + OPDS catalog. {LAN_WARNING}",
    lifespan=lifespan,
)


class DeviceAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        path = request.url.path
        if is_device_path(path):
            client = request.client.host if request.client else "unknown"
            record_access(
                client_ip=client,
                user_agent=request.headers.get("user-agent"),
                method=request.method,
                path=path,
                status_code=response.status_code,
            )
        return response


app.add_middleware(DeviceAccessMiddleware)


class SourceConfigUpdate(BaseModel):
    config: dict[str, Any]


class SettingsUpdate(BaseModel):
    sync_hour: int | None = Field(default=None, ge=0, le=23)
    sync_minute: int | None = Field(default=None, ge=0, le=59)
    max_articles: int | None = Field(default=None, ge=1, le=200)
    opds_title: str | None = Field(default=None, min_length=1, max_length=120)
    digest_retention: int | None = Field(default=None, ge=1, le=365)


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _request_port(request: Request) -> int:
    return request.url.port or (443 if request.url.scheme == "https" else PORT)


def _lan_base_url(request: Request) -> str | None:
    ip = primary_lan_ipv4()
    if not ip:
        return None
    port = _request_port(request)
    scheme = request.url.scheme or "http"
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{ip}"
    return f"{scheme}://{ip}:{port}"


@app.get("/api/status")
def api_status(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    active = get_active_source_row(session)
    last = session.exec(select(Run).order_by(desc(Run.started_at))).first()
    source = SOURCES.get(active.source_id) if active else None
    config = load_json(active.config_json) if active else {}
    configured = False
    if source and active:
        configured = not source.validate_config(config)
    lan_ip = primary_lan_ipv4()
    lan_base = _lan_base_url(request)
    request_base = _base_url(request)
    site_url = lan_base or request_base
    return {
        "ok": True,
        "warning": LAN_WARNING,
        "active_source_id": active.source_id if active else None,
        "active_source_name": source.display_name if source else None,
        "source_configured": configured,
        "run_in_progress": is_run_in_progress(),
        "last_run": serialize_run(last) if last else None,
        "next_run_at": next_run_iso(),
        "lan_ip": lan_ip,
        "lan_ips": lan_ipv4_addresses(),
        "site_url": site_url,
        "opds_url": f"{site_url}/opds",
        "latest_digest": last.digest_filename if last and last.digest_filename else None,
    }


@app.get("/api/devices")
def api_list_devices() -> list[dict[str, Any]]:
    return list_devices()


@app.get("/api/devices/events")
def api_list_device_events(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    return list_events(limit)


@app.get("/api/runs")
def api_list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.exec(select(Run).order_by(desc(Run.started_at)).limit(limit)).all()
    return [serialize_run(row) for row in rows]


@app.get("/api/runs/{run_id}")
def api_get_run(run_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run.articles  # load relationship
    return serialize_run(run, include_articles=True)


@app.get("/api/runs/{run_id}/articles")
def api_run_articles(run_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    rows = session.exec(
        select(ArticleRecord).where(ArticleRecord.run_id == run_id).order_by(ArticleRecord.id)
    ).all()
    return [serialize_article(row) for row in rows]


@app.post("/api/runs/trigger", status_code=202)
async def api_trigger_run() -> dict[str, Any]:
    try:
        run = await trigger_run()
    except RunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_run(run)


@app.get("/api/sources")
def api_list_sources(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = {row.source_id: row for row in session.exec(select(SourceConfig)).all()}
    result = []
    for source_id, source in SOURCES.items():
        row = rows.get(source_id)
        config = load_json(row.config_json) if row else {}
        result.append(
            {
                "source_id": source.source_id,
                "display_name": source.display_name,
                "is_active": bool(row and row.is_active),
                "configured": not source.validate_config(config),
                "config_fields": [field.__dict__ for field in source.config_fields()],
            }
        )
    return result


@app.get("/api/sources/{source_id}/config")
def api_get_source_config(source_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    if source_id not in SOURCES:
        raise HTTPException(status_code=404, detail="Unknown source")
    row = session.exec(select(SourceConfig).where(SourceConfig.source_id == source_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Source has no stored config yet")
    config = load_json(row.config_json)
    return {
        "source_id": source_id,
        "is_active": row.is_active,
        "config": mask_config(config),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "secrets_set": [k for k, v in config.items() if k in {"api_key", "password", "token", "secret"} and v],
    }


@app.put("/api/sources/{source_id}/config")
def api_put_source_config(
    source_id: str,
    body: SourceConfigUpdate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if source_id not in SOURCES:
        raise HTTPException(status_code=404, detail="Unknown source")
    row = session.exec(select(SourceConfig).where(SourceConfig.source_id == source_id)).first()
    if row is None:
        row = SourceConfig(source_id=source_id, is_active=False, config_json="{}")
        session.add(row)
        session.flush()
    merged = merge_config(load_json(row.config_json), body.config)
    row.config_json = json.dumps(merged)
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return {
        "source_id": source_id,
        "is_active": row.is_active,
        "config": mask_config(merged),
        "problems": SOURCES[source_id].validate_config(merged),
    }


@app.post("/api/sources/{source_id}/activate")
def api_activate_source(source_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    if source_id not in SOURCES:
        raise HTTPException(status_code=404, detail="Unknown source")
    row = activate_source(session, source_id)
    return {"source_id": row.source_id, "is_active": True}


@app.post("/api/sources/{source_id}/validate")
def api_validate_source(
    source_id: str,
    body: SourceConfigUpdate | None = Body(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if source_id not in SOURCES:
        raise HTTPException(status_code=404, detail="Unknown source")
    source = get_source(source_id)
    row = session.exec(select(SourceConfig).where(SourceConfig.source_id == source_id)).first()
    stored = load_json(row.config_json) if row else {}
    config = merge_config(stored, body.config) if body else stored
    problems = source.validate_config(config)
    return {"ok": not problems, "problems": problems}


@app.get("/api/settings")
def api_get_settings(session: Session = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings_map(session)
    return {
        "sync_hour": int(settings["sync_hour"]),
        "sync_minute": int(settings["sync_minute"]),
        "max_articles": int(settings["max_articles"]),
        "opds_title": settings["opds_title"],
        "digest_retention": int(settings["digest_retention"]),
        "active_source_id": settings["active_source_id"],
    }


@app.put("/api/settings")
def api_put_settings(
    body: SettingsUpdate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from models import AppSetting

    current = get_settings_map(session)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "opds_title" in updates:
        current["opds_title"] = str(updates["opds_title"]).strip()
    for key in ("sync_hour", "sync_minute", "max_articles", "digest_retention"):
        if key in updates:
            current[key] = str(int(updates[key]))
    for key, value in current.items():
        row = session.get(AppSetting, key)
        if row:
            row.value = value
            session.add(row)
        else:
            session.add(AppSetting(key=key, value=value))
    session.commit()
    reschedule_from_db()
    return api_get_settings(session)


@app.get("/api/digests")
def api_list_digests(request: Request) -> list[dict[str, Any]]:
    files = list_digest_files()
    return [
        {
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "download_url": f"{_base_url(request)}/api/digests/{path.name}/download",
            "opds_download_url": f"{_base_url(request)}/download/{path.name}",
        }
        for path in files
    ]


@app.get("/api/digests/{filename}/download")
def api_download_digest(filename: str) -> FileResponse:
    return _serve_digest(filename)


@app.get("/opds")
def opds_catalog(request: Request, session: Session = Depends(get_session)) -> Response:
    settings = get_settings_map(session)
    xml = build_opds_feed(title=settings.get("opds_title") or "eink-news-sync", base_url=_base_url(request))
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")


@app.get("/download/{filename}")
def download_digest(filename: str) -> FileResponse:
    return _serve_digest(filename)


def _serve_digest(filename: str) -> FileResponse:
    if not SAFE_DIGEST.match(filename):
        raise HTTPException(status_code=400, detail="Invalid digest filename")
    path = DIGESTS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Digest not found")
    return FileResponse(path, media_type="application/epub+zip", filename=filename)


if FRONTEND_DIST.is_dir():
    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        index = FRONTEND_DIST / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="Frontend not built")
        return FileResponse(index)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=not TESTING)

# eink-news-sync — Technical Spec

## 1. Purpose

A self-hosted service, running in Docker on a home network, that:
- Pulls current news articles from a pluggable **source** (Guardian Open Platform to start; FT and others later).
- Builds a daily digest EPUB.
- Serves it via an OPDS catalog for an e-reader to pull.
- Exposes a local web UI for configuration, run history, and browsing what was fetched.

Single user, single device. No auth hardening beyond "don't expose this to the internet" is in scope for v1.

## 2. Non-negotiable design constraint

The e-reader is not always reachable — it sleeps and only runs its own web server when a human puts it into File Transfer/OPDS mode. So delivery is **pull-based**: this service always has the latest digest ready at a stable OPDS URL; the device fetches on its own schedule (manual, for now).

## 3. High-level architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Docker container(s)                  │
│                                                            │
│  ┌───────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │ Scheduler │──▶│ Source Layer │──▶│  Digest Builder  │  │
│  │ (APSched) │   │ (pluggable)  │   │  (EPUB writer)   │  │
│  └───────────┘   └──────────────┘   └─────────────────┘  │
│        │                 │                    │           │
│        ▼                 ▼                    ▼           │
│  ┌────────────────────────────────────────────────────┐  │
│  │              SQLite (config, runs, articles)         │  │
│  └────────────────────────────────────────────────────┘  │
│        │                                       │           │
│        ▼                                       ▼           │
│  ┌───────────┐                        ┌─────────────────┐ │
│  │ REST API  │◀──────────────────────▶│  OPDS + file     │ │
│  │ (backend) │                        │  download server │ │
│  └───────────┘                        └─────────────────┘ │
│        ▲                                                   │
│        │                                                   │
│  ┌───────────┐                                             │
│  │  Web UI   │  (served statically or on its own port)     │
│  └───────────┘                                             │
└─────────────────────────────────────────────────────────┘
         ▲                                        ▲
         │ browser (you)                          │ OPDS client
         │                                         │ (e-reader)
```

Recommend a **single backend process** (Python) exposing both the REST API and the OPDS/file endpoints, plus a separate lightweight frontend (static SPA) served either by the same backend or its own nginx container. Keep it to one backend service for v1 — don't over-decompose into microservices for a single-user home app.

### 3.1 Technology stack

Concrete choices, not open-ended — the implementing agent should use these unless one turns out to be genuinely unworkable, in which case flag the substitution rather than silently swapping it.

| Concern | Choice | Why |
|---|---|---|
| Backend language/runtime | Python 3.12 | Matches the earlier prototype; strong EPUB/HTTP ecosystem. |
| Web framework | FastAPI | Async, free OpenAPI docs at `/docs` (useful for a solo dev debugging the API), typed request/response models via Pydantic. |
| ASGI server | uvicorn | Standard FastAPI pairing; run via `uvicorn main:app`. |
| ORM / DB models | SQLModel | Pydantic + SQLAlchemy in one model definition — the `Article`/`ArticleStub` dataclasses in §4 and the DB tables in §5 can share the same class instead of hand-mapping between two representations. |
| Database | SQLite (file on the `/data` volume) | Single-user, single-host, zero-ops. No Postgres/MySQL needed. |
| Schema migrations | `SQLModel.metadata.create_all()` on startup for v1 | No migration framework needed yet — there's no production data to preserve across schema changes while this is a single evolving app. Note in code that Alembic should be introduced if/when the schema needs to change after real digests have accumulated. |
| Scheduler | APScheduler (`AsyncIOScheduler`, integrated into FastAPI's event loop) | Matches §8; avoids a separate cron container/process. |
| HTTP client (for source APIs) | httpx | Async-friendly, works cleanly inside FastAPI/APScheduler async jobs. |
| EPUB generation | ebooklib | Matches the earlier prototype; well-supported, simple chapter/spine API. |
| OPDS feed generation | Hand-written Atom/XML via Python's `xml.etree.ElementTree` or f-strings | The feed shape is small and fixed (see §7) — a full OPDS library is unnecessary weight for this. |
| Frontend framework | React + TypeScript, built with Vite | Modern, fast local dev loop, no server-side rendering complexity needed for a local dashboard. |
| Frontend styling | Tailwind CSS | Fast to build a clean utility-driven UI without a component library dependency; add shadcn/ui components only if the forms/tables in §10 need more polish than plain Tailwind gives easily. |
| Frontend data fetching | Plain `fetch` against `/api/*`, or TanStack Query if polling (e.g. run status while a sync is in progress) gets unwieldy with plain fetch | Keep it minimal until the UI actually needs caching/refetch logic. |
| Frontend hosting | Static build (`vite build`) served by FastAPI's `StaticFiles`, same origin as the API | Avoids CORS configuration and keeps it one container, one port. |
| Containerization | Single multi-stage `Dockerfile`: stage 1 builds the frontend (`node:20-slim`), stage 2 is `python:3.12-slim` copying the built frontend + backend | One image, one `docker-compose.yml` service, one `/data` volume — matches the "keep it to one backend service" guidance above. |
| Testing | `pytest` for backend (source adapters, digest builder, API routes); no frontend test framework mandated for v1 | Prioritize backend correctness — that's where a broken source integration silently produces empty digests. |

## 4. Source abstraction (the core extensibility requirement)

Define a `NewsSource` interface that all providers implement. This is the seam that makes "add FT later" cheap.

```python
class Article:
    source_id: str          # e.g. "guardian"
    external_id: str        # source's own article id/url, used for de-duplication
    title: str
    url: str
    section: str | None
    published_at: datetime
    byline: str | None
    body_text: str          # plain text or simple HTML, already de-paywalled/de-boilerplated
    body_html: str | None   # optional richer version for EPUB rendering

class NewsSource(ABC):
    source_id: str          # stable slug, e.g. "guardian", "ft"
    display_name: str       # e.g. "The Guardian"

    def get_headlines(self, config: dict, max_items: int) -> list[ArticleStub]:
        """Cheap call: list of candidate articles (id, title, url, section) without full body."""

    def fetch_article(self, config: dict, stub: ArticleStub) -> Article | None:
        """Expensive call: full article body. Returns None if unavailable/paywalled/failed."""

    def validate_config(self, config: dict) -> list[str]:
        """Return list of human-readable config problems, empty if OK. Used by the UI to
        show "this source isn't configured correctly" before a run fails silently."""
```

Each source is registered in a small registry (`SOURCES = {"guardian": GuardianSource(), "ft": FTSource(), ...}`) keyed by `source_id`. The digest builder and scheduler never import a specific source directly — they look it up by whatever `source_id` is active in config.

**v1 ships exactly one implementation: `GuardianSource`.** Build the interface now, but don't build a second source yet — that's explicitly deferred.

### GuardianSource specifics
- Uses The Guardian Open Platform Content API (`https://content.guardianapis.com/search`), free tier, API key from the user.
- `get_headlines`: query `search` endpoint filtered by configured section(s) and a lookback window (e.g. last 24h), ordered by newest, `page-size` capped by `max_items`.
- `fetch_article`: the search endpoint can return full body in one call via `show-fields=body,byline,trailText` — so in practice `get_headlines` and `fetch_article` may collapse into one API call per query rather than two round trips. Structure the code so this optimization is possible (i.e., `get_headlines` is allowed to pre-populate the body if the source got it for free, and `fetch_article` just returns the cached copy in that case).
- Config fields: `api_key` (required, secret), `sections` (list of Guardian section tags, e.g. `world`, `business`, `technology`), `lookback_hours` (default 24).

## 5. Data model (SQLite)

Keep it boring — a single SQLite file, no external DB dependency, for a single-user home service.

```
sources_config
  id (pk)
  source_id            text            -- "guardian"
  is_active            bool            -- only one active at a time in v1
  config_json          text            -- {"api_key": "...", "sections": [...], ...}
  updated_at           datetime

runs
  id (pk)
  started_at           datetime
  finished_at          datetime null
  status               text            -- "running" | "success" | "error" | "partial"
  source_id            text
  articles_fetched     int
  articles_failed      int
  error_message        text null
  digest_filename      text null       -- e.g. "digest-2026-08-18.epub"

articles
  id (pk)
  run_id               fk -> runs.id
  source_id            text
  external_id          text
  title                text
  url                  text
  section              text null
  published_at         datetime null
  byline                text null
  fetch_status          text          -- "ok" | "skipped_paywall" | "failed"
  word_count            int null

app_settings
  key (pk)              text          -- "sync_hour", "sync_minute", "max_articles",
                                          "opds_title", "active_source_id"
  value                  text
```

Rationale: `runs` + `articles` gives the UI a real history view ("last 30 syncs, what got pulled, what failed and why") without needing log-scraping. This is most of what makes the "see data" part of the ask useful.

## 6. Digest builder

- Input: list of `Article` objects from the current run.
- Output: single EPUB (`ebooklib`), one chapter per article, title page includes date + source name + article count.
- Naming: `digest-YYYY-MM-DD.epub`, stored under `/data/digests/`.
- Keep only the last N digests on disk (configurable, default 14) — delete older files on each successful run to avoid unbounded growth on the eReader's SD-mirrored downloads folder.
- Digest builder is source-agnostic — it only depends on the `Article` dataclass, not on any specific `NewsSource`.

## 7. Delivery: OPDS + downloads

- `GET /opds` — Atom/OPDS catalog. Root feed lists available digests (most recent first, e.g. last 7), each with an acquisition link.
- `GET /download/{filename}` — serves the EPUB file.
- No auth (do not expose this to the internet). Document this assumption prominently in the README/UI ("do not port-forward this").

## 8. Scheduler

- APScheduler cron trigger, configurable hour/minute via settings (persisted in `app_settings`, editable from the UI — not just env vars, since one of the goals is UI-driven config).
- One run = one source (whatever's marked `is_active`). Multi-source blending is explicitly out of scope for v1 (see §11).
- Manual trigger endpoint (`POST /api/runs/trigger`) for testing/on-demand rebuilds, used by both curl and the UI's "Sync now" button.
- Only one run at a time; a trigger while a run is in progress returns 409, not a queued duplicate.

## 9. REST API (backend, consumed by the frontend)

All under `/api`. JSON in/out.

```
GET  /api/status                  -- overall health: last run summary, next scheduled run, active source
GET  /api/runs?limit=50           -- run history, most recent first
GET  /api/runs/{id}               -- run detail incl. article list
GET  /api/runs/{id}/articles      -- articles for a run (title, url, section, fetch_status, word_count)
POST /api/runs/trigger            -- manual sync now

GET  /api/sources                 -- list of registered source_ids + display names + which is active
GET  /api/sources/{id}/config     -- current config for a source (secrets masked)
PUT  /api/sources/{id}/config     -- update config for a source
POST /api/sources/{id}/activate   -- set as the active source
POST /api/sources/{id}/validate   -- run validate_config() and return problems, without doing a real fetch

GET  /api/settings                -- sync_hour, sync_minute, max_articles, opds_title, retention count
PUT  /api/settings                -- update settings

GET  /api/digests                 -- list of digests on disk with size/date, mirrors OPDS but for the UI
GET  /api/digests/{filename}/download   -- same file as /download/{filename}, for UI's own download button

GET  /opds                        -- OPDS catalog (device-facing, not prefixed with /api)
GET  /download/{filename}         -- EPUB download (device-facing)
```

Secrets (API keys) are stored server-side only; `GET config` endpoints return them masked (e.g. `sk_live_••••1234`) and the UI never round-trips the real value unless the user is actively changing it.

## 10. Frontend (local web UI)

Single-page app, served locally (same origin as the API is simplest — avoid CORS complexity for v1). No login — do not expose this tool.

**Pages/views:**

1. **Dashboard** — active source, last run status (success/error, timestamp, article count), next scheduled run, "Sync now" button, link to latest digest.
2. **Run history** — table of past runs (date, source, status, articles fetched/failed, duration). Click through to a run detail view listing every article attempted with its fetch status (fetched / skipped / failed) — this is the primary debugging surface when a source's parsing breaks.
3. **Source configuration** — form for the active source's config fields (API key, sections, lookback window, etc.), driven generically by `validate_config()` rather than hardcoded per source where possible, so adding a second source later doesn't require frontend changes beyond a new source appearing in a dropdown. "Test configuration" button calls `POST /api/sources/{id}/validate`.
4. **Settings** — sync schedule, max articles per digest, digest retention count, OPDS catalog title.
5. **Digests** — list of built EPUBs with download links and the OPDS URL to paste into the device.

Keep this simple: server-rendered templates or a small React/vanilla JS app are both fine — no strong opinion, but avoid a heavy build pipeline for a single-user local tool. A reasonable default: FastAPI (or Flask) backend serving both the JSON API and a small static frontend bundle from the same container.

## 11. Explicitly out of scope for v1

- Multiple sources active simultaneously / merged digests. (Interface supports it later; scheduler and digest builder do not need to handle it now.)
- Authentication/authorization on the web UI or OPDS endpoints.
- Push delivery to the device (not possible given device sleep behavior — see §2).
- Per-article read/unread sync back from the device.
- Any content beyond plain text + basic formatting (no embedded images in v1, to keep EPUB size small for the e-ink device).

## 12. Config / environment

Minimal env vars for bootstrapping only (everything else lives in SQLite via the UI, so it survives container restarts and doesn't require redeploys to change):

```
DATA_DIR=/data                 # sqlite db + digests live here, single volume to persist
PORT=8080
```

Guardian API key, sections, schedule, etc. are all set through the UI after first boot, not through `docker-compose.yml` env vars — the whole point of the UI is to avoid editing compose files for routine config changes.

## 13. Directory structure (suggested)

```
eink-news-sync/
  backend/
    main.py                  # FastAPI/Flask app, mounts API + OPDS routes
    models.py                 # SQLite schema / ORM models
    scheduler.py
    digest_builder.py
    sources/
      __init__.py             # registry
      base.py                 # NewsSource ABC, Article/ArticleStub dataclasses
      guardian.py
  frontend/
    ...                       # SPA source
  data/                        # volume-mounted, gitignored
  Dockerfile
  docker-compose.yml
  README.md
```

## 14. Open questions for the implementing agent to flag back, not guess silently on

- Whether digests should include Guardian's `trailText` as an article summary/subtitle in the EPUB.
- Exact Guardian sections to default to on first boot (spec leaves this empty/user-configured rather than hardcoded).
- Whether each article should ship as a separate EPUB (separate library/OPDS entries) instead of one chapter-per-article digest file — current spec (§6) assumes one combined daily EPUB; confirm before building if the per-article-file layout is preferred instead.

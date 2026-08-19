# eink-news-sync

Self-hosted daily news digest for a LAN e-reader.

The service pulls articles from a pluggable source (The Guardian in v1), builds one EPUB per day, and serves it over OPDS so a Xteink X3 (CrossPoint firmware) can pull it when you put the device into File Transfer/OPDS mode.

**Do not port-forward this. Do not expose it to the internet.** There is no authentication in v1. It is meant to listen on your home LAN only.

## Quick start (Distrobox / Distro Shelf)

Use the **dev-box** container from Distro Shelf. Docker is installed there, but this Distrobox cannot run nested containers (`network namespace: operation not permitted`), so run the app directly inside the box:

```bash
distrobox enter dev-box
cd ~/apps/Article-getter
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
mkdir -p data
DATA_DIR="$(pwd)/data" PYTHONPATH="$(pwd)/backend" \
  uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8080
```

1. Go to **Source** and paste a Guardian Open Platform API key ([free signup](https://open-platform.theguardian.com/access/)).
2. Optionally set sections (`world`, `business`, `technology`, …) and lookback hours.
3. Click **Test configuration**, then **Save**.
4. Hit **Sync now** on the dashboard.
5. On the device, add the OPDS catalog URL shown on the dashboard: `http://<your-lan-ip>:8080/opds`.

Data (SQLite + EPUBs) lives in `./data` on the host, mounted at `/data` in the container.

## Local development

Backend (from repo root):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
DATA_DIR=../data uvicorn main:app --reload --port 8080
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api`, `/opds`, and `/download` to port 8080.

API docs: `http://127.0.0.1:8080/docs`.

Tests:

```bash
TESTING=1 DATA_DIR=/tmp/eink-news-test pytest
```

## How delivery works

The e-reader sleeps and only runs its web server in File Transfer/OPDS mode, so this service never pushes. It always has the latest digest ready at a stable URL:

- Catalog: `GET /opds`
- File: `GET /download/digest-YYYY-MM-DD.epub`

Re-running a sync on the same day overwrites that day’s file, so the OPDS entry stays stable.

## Configuration

Bootstrapping env vars only:

| Variable   | Default | Purpose                                      |
|------------|---------|----------------------------------------------|
| `DATA_DIR` | `/data` | SQLite DB + `digests/` directory             |
| `PORT`     | `8080`  | Listen port                                  |

Guardian API key, sections, schedule, max articles, retention, and OPDS title are stored in SQLite and edited in the UI. They survive container restarts.

Default schedule is 06:00 in the **server’s local timezone**.

## Layout

```
backend/          FastAPI app, scheduler, Guardian adapter, EPUB builder
frontend/         React + Vite + Tailwind SPA (served by FastAPI in Docker)
data/             volume (gitignored)
```

Adding a second source later means implementing `NewsSource` in `backend/sources/` and registering it in `backend/sources/__init__.py`. The scheduler, digest builder, OPDS feed, and UI form are source-agnostic.

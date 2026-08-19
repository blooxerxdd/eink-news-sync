import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
PORT = int(os.environ.get("PORT", "8080"))
TESTING = os.environ.get("TESTING", "").lower() in {"1", "true", "yes"}

DB_PATH = DATA_DIR / "eink-news-sync.db"
DIGESTS_DIR = DATA_DIR / "digests"

# Defaults written into app_settings on first boot. Everything else is UI-driven.
DEFAULT_SETTINGS: dict[str, str] = {
    "sync_hour": "6",
    "sync_minute": "0",
    "max_articles": "20",
    "opds_title": "eink-news-sync",
    "digest_retention": "14",
    "active_source_id": "guardian",
}

ACCESS_EVENT_LIMIT = 1000
DEVICE_RECENT_SECONDS = 5 * 60
OPDS_FEED_LIMIT = 7
SECRET_CONFIG_KEYS = {"api_key", "password", "token", "secret"}

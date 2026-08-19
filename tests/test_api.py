from unittest.mock import AsyncMock, patch

from scheduler import RunInProgress
from util import looks_masked, mask_secret, merge_config


def test_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["active_source_id"] == "guardian"
    assert "do not port-forward" in body["warning"].lower()
    assert "lan_ip" in body
    assert "site_url" in body
    assert body["opds_url"].endswith("/opds")


def test_sources_list_includes_schema(client):
    response = client.get("/api/sources")
    assert response.status_code == 200
    sources = response.json()
    assert sources[0]["source_id"] == "guardian"
    keys = {field["key"] for field in sources[0]["config_fields"]}
    assert keys == {"api_key", "sections", "lookback_hours"}


def test_config_roundtrip_masks_secret(client):
    put = client.put(
        "/api/sources/guardian/config",
        json={"config": {"api_key": "super-secret-key", "sections": ["world"], "lookback_hours": 24}},
    )
    assert put.status_code == 200
    masked = put.json()["config"]["api_key"]
    assert masked.startswith("••••")
    assert "super-secret" not in masked

    fetched = client.get("/api/sources/guardian/config")
    assert fetched.json()["config"]["api_key"] == masked
    assert "api_key" in fetched.json()["secrets_set"]

    # Sending the masked value back must not wipe the real key.
    put2 = client.put(
        "/api/sources/guardian/config",
        json={"config": {"api_key": masked, "sections": ["world", "business"]}},
    )
    assert put2.status_code == 200
    stored = client.get("/api/sources/guardian/config").json()
    assert stored["config"]["sections"] == ["world", "business"]
    assert stored["config"]["api_key"].endswith("key")


def test_validate_source(client):
    response = client.post(
        "/api/sources/guardian/validate",
        json={"config": {"api_key": "x", "lookback_hours": 0}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert any("Lookback" in p for p in body["problems"])


def test_settings_update(client):
    response = client.put("/api/settings", json={"sync_hour": 7, "max_articles": 12, "digest_retention": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["sync_hour"] == 7
    assert body["max_articles"] == 12
    assert body["digest_retention"] == 5


def test_trigger_conflict_when_locked(client):
    with patch(
        "main.trigger_run",
        new=AsyncMock(side_effect=RunInProgress("A sync is already in progress")),
    ):
        response = client.post("/api/runs/trigger")
        assert response.status_code == 409


def test_opds_feed(client):
    response = client.get("/opds")
    assert response.status_code == 200
    assert "application/atom+xml" in response.headers["content-type"]
    assert b"<feed" in response.content
    assert b"eink-news-sync" in response.content or b"No digests" in response.content


def test_opds_hit_appears_in_device_log(client):
    client.get("/opds", headers={"User-Agent": "OPDS-Test/1.0"})
    devices = client.get("/api/devices").json()
    assert devices
    assert any(row["last_path"] == "/opds" for row in devices)
    events = client.get("/api/devices/events").json()
    assert events
    assert events[0]["path"] == "/opds"
    assert events[0]["status_code"] == 200
    assert events[0]["user_agent"] == "OPDS-Test/1.0"


def test_api_status_is_not_logged_as_device(client):
    client.get("/api/status")
    events = client.get("/api/devices/events").json()
    assert all(not event["path"].startswith("/api/") for event in events)


def test_download_rejects_invalid_filename(client):
    response = client.get("/download/not-a-digest.epub")
    assert response.status_code == 400


def test_mask_helpers():
    assert mask_secret("abcd1234") == "••••1234"
    assert looks_masked("••••1234")
    merged = merge_config({"api_key": "real"}, {"api_key": "••••real", "sections": ["world"]})
    assert merged["api_key"] == "real"
    assert merged["sections"] == ["world"]

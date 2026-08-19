from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sources.arjay_blog import ArjayBlogSource, item_to_stub

BASE = "https://blog.arjaythedev.com"

PAGE1 = [
    {
        "id": "new-id",
        "web_title": "Newest post",
        "web_subtitle": "fresh",
        "slug": "newest-post",
        "override_scheduled_at": "2026-08-17T15:56:51.742Z",
        "created_at": "2026-08-17T15:37:24Z",
        "authors": [{"name": "Arjay McCandless"}],
    },
    {
        "id": "mid-id",
        "web_title": "Middle post",
        "web_subtitle": "",
        "slug": "middle-post",
        "override_scheduled_at": "2026-08-07T12:00:00Z",
        "created_at": "2026-08-07T11:00:00Z",
        "authors": [{"name": "Arjay McCandless"}],
    },
]
PAGE2 = [
    {
        "id": "old-id",
        "web_title": "Oldest post",
        "web_subtitle": "classic",
        "slug": "oldest-post",
        "override_scheduled_at": "2025-10-21T15:01:24.367Z",
        "created_at": "2025-10-21T14:00:00Z",
        "authors": [{"name": "Arjay McCandless"}],
    },
]


def _json_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_validate_config_accepts_defaults():
    source = ArjayBlogSource()
    assert source.validate_config({}) == []
    assert source.validate_config({"base_url": BASE, "chapter_order": "newest"}) == []


def test_validate_config_rejects_bad_values():
    source = ArjayBlogSource()
    problems = source.validate_config({"base_url": "not-a-url", "chapter_order": "sideways"})
    assert any("http(s)" in p for p in problems)
    assert any("Chapter order" in p for p in problems)


def test_item_to_stub_uses_listing_date_and_url():
    stub = item_to_stub(PAGE1[0], BASE)
    assert stub.external_id == f"{BASE}/p/newest-post"
    assert stub.url == stub.external_id
    assert stub.title == "Newest post"
    assert stub.trail_text == "fresh"
    assert stub.byline == "Arjay McCandless"
    assert stub.published_at == datetime(2026, 8, 17, 15, 56, 51, 742000, tzinfo=timezone.utc)


def test_item_to_stub_falls_back_to_created_at():
    stub = item_to_stub(
        {"web_title": "No schedule", "slug": "no-schedule", "created_at": "2026-01-02T00:00:00Z"},
        BASE,
    )
    assert stub.published_at == datetime(2026, 1, 2, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_get_headlines_walks_all_pages(monkeypatch):
    source = ArjayBlogSource()
    page1 = _json_response({"posts": PAGE1, "pagination": {"page": 1, "per_page": 50, "total": 3, "total_pages": 2}})
    page2 = _json_response({"posts": PAGE2, "pagination": {"page": 2, "per_page": 50, "total": 3, "total_pages": 2}})

    mock_client = AsyncMock()
    mock_client.get.side_effect = [page1, page2]
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: mock_client)

    stubs = await source.get_headlines({}, max_items=20)
    assert [s.title for s in stubs] == ["Newest post", "Middle post", "Oldest post"]
    assert mock_client.get.await_count == 2


@pytest.mark.asyncio
async def test_get_headlines_stops_at_known_ok_url(monkeypatch):
    source = ArjayBlogSource()
    page1 = _json_response({"posts": PAGE1, "pagination": {"page": 1, "per_page": 50, "total": 3, "total_pages": 2}})

    mock_client = AsyncMock()
    mock_client.get.return_value = page1
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: mock_client)

    known = {f"{BASE}/p/middle-post"}
    stubs = await source.get_headlines({}, max_items=20, known_ok_ids=known)
    assert [s.title for s in stubs] == ["Newest post"]
    mock_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_article_uses_trafilatura(monkeypatch):
    source = ArjayBlogSource()
    stub = item_to_stub(PAGE1[0], BASE)

    html_response = MagicMock()
    html_response.status_code = 200
    html_response.text = "<html><body><article><p>Extracted body.</p></article></body></html>"
    html_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = html_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: mock_client)
    monkeypatch.setattr(
        "sources.arjay_blog.trafilatura.extract",
        lambda *_args, **kwargs: "<p>Extracted body.</p>" if kwargs.get("output_format") == "html" else "Extracted body.",
    )

    article = await source.fetch_article({}, stub)
    assert article is not None
    assert article.body_text == "Extracted body."
    assert "Extracted body." in (article.body_html or "")
    assert article.published_at == stub.published_at


def _stub_article(item: dict):
    source = ArjayBlogSource()
    stub = item_to_stub(item, BASE)
    stub.body_text = f"Body of {stub.title}"
    stub.body_html = f"<p>Body of {stub.title}</p>"
    return source.stub_to_article(stub)


def test_organize_digest_order_toggle():
    source = ArjayBlogSource()
    newest = _stub_article(PAGE1[0])
    oldest = _stub_article(PAGE2[0])
    assert newest is not None and oldest is not None
    oldest_first = source.organize_digest([newest, oldest], {"chapter_order": "oldest"})
    newest_first = source.organize_digest([newest, oldest], {"chapter_order": "newest"})
    assert [a.title for a in oldest_first[0][1]] == ["Oldest post", "Newest post"]
    assert [a.title for a in newest_first[0][1]] == ["Newest post", "Oldest post"]
    assert oldest_first[0][0] == ""

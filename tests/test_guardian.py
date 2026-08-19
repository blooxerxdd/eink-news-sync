from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sources.guardian import GuardianSource, _item_to_stub


SAMPLE_ITEM = {
    "id": "world/2026/aug/18/example-story",
    "sectionId": "world",
    "sectionName": "World news",
    "webPublicationDate": "2026-08-18T12:00:00Z",
    "webTitle": "Example headline",
    "webUrl": "https://www.theguardian.com/world/2026/aug/18/example-story",
    "fields": {
        "body": "<p>Hello <strong>world</strong>.</p>",
        "byline": "A. Reporter",
        "trailText": "A short summary.",
        "wordcount": "42",
    },
}


def test_validate_config_requires_api_key():
    source = GuardianSource()
    problems = source.validate_config({})
    assert any("API key" in p for p in problems)


def test_validate_config_ok():
    source = GuardianSource()
    assert source.validate_config({"api_key": "test", "sections": ["world"], "lookback_hours": 24}) == []


def test_item_to_stub_extracts_body():
    stub = _item_to_stub(SAMPLE_ITEM)
    assert stub.external_id == "world/2026/aug/18/example-story"
    assert stub.body_text == "Hello world."
    assert stub.trail_text == "A short summary."
    assert stub.word_count == 42
    assert stub.published_at == datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_get_headlines_and_cached_fetch(monkeypatch):
    source = GuardianSource()
    payload = {"response": {"status": "ok", "pages": 1, "results": [SAMPLE_ITEM]}}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: mock_client)

    stubs = await source.get_headlines({"api_key": "test", "sections": ["world"], "lookback_hours": 24 * 365}, max_items=5)
    assert len(stubs) == 1
    assert stubs[0].title == "Example headline"

    article = await source.fetch_article({"api_key": "test"}, stubs[0])
    assert article is not None
    assert article.body_html.startswith("<p>Hello")
    assert article.section == "World news"
    assert article.section_id == "world"
    mock_client.get.assert_awaited_once()


def test_item_to_stub_prefers_section_display_name():
    stub = _item_to_stub(SAMPLE_ITEM)
    assert stub.section == "World news"
    assert stub.section_id == "world"


def test_organize_digest_follows_configured_section_order():
    source = GuardianSource()
    articles = [
        source.stub_to_article(
            _item_to_stub({**SAMPLE_ITEM, "id": "science/1", "sectionId": "science", "sectionName": "Science", "webTitle": "Sci"})
        ),
        source.stub_to_article(
            _item_to_stub({**SAMPLE_ITEM, "id": "world/1", "sectionId": "world", "sectionName": "World news", "webTitle": "World"})
        ),
        source.stub_to_article(
            _item_to_stub({**SAMPLE_ITEM, "id": "business/1", "sectionId": "business", "sectionName": "Business", "webTitle": "Biz"})
        ),
    ]
    fetched = [a for a in articles if a is not None]
    groups = source.organize_digest(fetched, {"sections": ["business", "world"]})
    assert [label for label, _ in groups] == ["Business", "World news", "Science"]
    assert [a.title for a in groups[0][1]] == ["Biz"]

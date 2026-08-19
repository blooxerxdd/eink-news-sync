from datetime import datetime, timezone
from pathlib import Path

from digest_builder import build_digest, prune_digests
from sources.base import Article


def _article(n: int) -> Article:
    return Article(
        source_id="guardian",
        external_id=f"id-{n}",
        title=f"Story {n}",
        url=f"https://example.com/{n}",
        section="world",
        published_at=datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
        byline="A. Reporter",
        body_text=f"Body of story {n}.",
        body_html=f"<p>Body of story {n}.</p>",
        trail_text=f"Summary {n}",
        word_count=4,
    )


def test_build_digest_writes_epub(tmp_path: Path):
    path = build_digest(
        [_article(1), _article(2)],
        output_dir=tmp_path,
        source_name="The Guardian",
        digest_date=datetime(2026, 8, 18).date(),
    )
    assert path.name == "digest-2026-08-18.epub"
    assert path.is_file()
    assert path.stat().st_size > 100


def test_prune_keeps_newest(tmp_path: Path):
    for day in range(10, 20):
        (tmp_path / f"digest-2026-08-{day}.epub").write_bytes(b"fake")
    deleted = prune_digests(tmp_path, retention=3)
    remaining = sorted(p.name for p in tmp_path.glob("digest-*.epub"))
    assert remaining == [
        "digest-2026-08-17.epub",
        "digest-2026-08-18.epub",
        "digest-2026-08-19.epub",
    ]
    assert "digest-2026-08-10.epub" in deleted

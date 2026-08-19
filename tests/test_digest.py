from datetime import datetime, timezone
from pathlib import Path

from digest_builder import build_digest, parse_digest_filename, prune_digests
from sources.base import Article


def _article(n: int, source_id: str = "guardian") -> Article:
    return Article(
        source_id=source_id,
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


def test_build_digest_writes_epub_per_source(tmp_path: Path):
    path = build_digest(
        [_article(1), _article(2)],
        output_dir=tmp_path,
        source_name="The Guardian",
        source_id="guardian",
        digest_date=datetime(2026, 8, 18).date(),
    )
    assert path.name == "digest-2026-08-18-guardian.epub"
    assert path.is_file()
    assert path.stat().st_size > 100


def test_two_sources_write_distinct_files(tmp_path: Path):
    guardian = build_digest(
        [_article(1, "guardian")],
        output_dir=tmp_path,
        source_name="The Guardian",
        source_id="guardian",
        digest_date=datetime(2026, 8, 18).date(),
    )
    ft = build_digest(
        [_article(2, "ft")],
        output_dir=tmp_path,
        source_name="Financial Times",
        source_id="ft",
        digest_date=datetime(2026, 8, 18).date(),
    )
    assert guardian.name == "digest-2026-08-18-guardian.epub"
    assert ft.name == "digest-2026-08-18-ft.epub"
    assert guardian.is_file() and ft.is_file()


def test_prune_keeps_newest_per_source(tmp_path: Path):
    for day in range(10, 20):
        (tmp_path / f"digest-2026-08-{day}-guardian.epub").write_bytes(b"g")
        (tmp_path / f"digest-2026-08-{day}-ft.epub").write_bytes(b"f")
    deleted = prune_digests(tmp_path, retention=3)
    remaining = sorted(p.name for p in tmp_path.glob("digest-*.epub"))
    assert remaining == [
        "digest-2026-08-17-ft.epub",
        "digest-2026-08-17-guardian.epub",
        "digest-2026-08-18-ft.epub",
        "digest-2026-08-18-guardian.epub",
        "digest-2026-08-19-ft.epub",
        "digest-2026-08-19-guardian.epub",
    ]
    assert "digest-2026-08-10-guardian.epub" in deleted
    assert "digest-2026-08-10-ft.epub" in deleted


def test_parse_legacy_and_source_filenames():
    assert parse_digest_filename("digest-2026-08-18.epub") == ("2026-08-18", "")
    assert parse_digest_filename("digest-2026-08-18-guardian.epub") == ("2026-08-18", "guardian")
    assert parse_digest_filename("not-a-digest.epub") is None

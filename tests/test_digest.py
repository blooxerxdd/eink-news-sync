import zipfile
from datetime import datetime, timezone
from pathlib import Path

from article_groups import group_articles_by_section
from digest_builder import build_digest, parse_digest_filename, prune_digests
from sources.base import Article


def _article(
    n: int,
    source_id: str = "guardian",
    *,
    section: str | None = "World news",
    section_id: str | None = "world",
    hour: int = 12,
    title: str | None = None,
) -> Article:
    return Article(
        source_id=source_id,
        external_id=f"id-{n}",
        title=title or f"Story {n}",
        url=f"https://example.com/{n}",
        section=section,
        published_at=datetime(2026, 8, 18, hour, 0, tzinfo=timezone.utc),
        byline="A. Reporter",
        body_text=f"Body of story {n}.",
        body_html=f"<p>Body of story {n}.</p>",
        trail_text=f"Summary {n}",
        word_count=4,
        section_id=section_id,
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


def test_group_articles_by_section_order_and_recency():
    science = _article(1, section="Science", section_id="science", hour=10)
    none = _article(2, section=None, section_id=None, hour=18)
    world_old = _article(3, section="World news", section_id="world", hour=8)
    business = _article(4, section="Business", section_id="business", hour=16)
    world_new = _article(5, section="World news", section_id="world", hour=20)

    groups = group_articles_by_section(
        [science, none, world_old, business, world_new],
        section_order=["world", "business"],
    )
    assert [label for label, _ in groups] == ["World news", "Business", "Science", "Other"]
    assert [a.title for a in groups[0][1]] == ["Story 5", "Story 3"]
    assert [a.title for a in groups[1][1]] == ["Story 4"]
    assert [a.title for a in groups[3][1]] == ["Story 2"]


def test_group_articles_unsectioned_is_one_unlabeled_group():
    groups = group_articles_by_section(
        [
            _article(1, section=None, section_id=None, hour=10),
            _article(2, section=None, section_id=None, hour=14),
        ]
    )
    assert len(groups) == 1
    assert groups[0][0] == ""
    assert [a.title for a in groups[0][1]] == ["Story 2", "Story 1"]


def test_build_digest_groups_sections_in_one_file(tmp_path: Path):
    articles = [
        _article(1, section="Science", section_id="science", hour=9),
        _article(2, section="World news", section_id="world", hour=11),
        _article(3, section="Business", section_id="business", hour=10),
    ]
    path = build_digest(
        articles,
        output_dir=tmp_path,
        source_name="The Guardian",
        source_id="guardian",
        digest_date=datetime(2026, 8, 18).date(),
        groups=group_articles_by_section(articles, section_order=["world", "business"]),
    )
    assert path.name == "digest-2026-08-18-guardian.epub"
    assert list(tmp_path.glob("digest-*.epub")) == [path]

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        nav = next(n for n in names if n.endswith("nav.xhtml"))
        title = next(n for n in names if n.endswith("title.xhtml"))
        world_divider = next(n for n in names if n.endswith("section_world-news.xhtml"))
        nav_text = zf.read(nav).decode()
        title_text = zf.read(title).decode()
        divider = zf.read(world_divider).decode()

    assert any(n.endswith("section_world-news.xhtml") for n in names)
    assert any(n.endswith("section_business.xhtml") for n in names)
    assert any(n.endswith("section_science.xhtml") for n in names)
    assert nav_text.find("World news") < nav_text.find("Business") < nav_text.find("Science")
    assert "World news — 1" in title_text
    assert "Business — 1" in title_text
    assert "<h1>World news</h1>" in divider

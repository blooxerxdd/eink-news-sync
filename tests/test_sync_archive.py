from datetime import datetime, timezone
from pathlib import Path

import zipfile
from sqlmodel import Session, select

from database import engine
from digest_builder import build_digest, is_allowed_epub_filename, prune_digests
from models import Run, SourcePost
from sources import SOURCES
from sources.base import Article, ArticleStub
from sync_job import execute_run
from util import activate_source


def _article(n: int) -> Article:
    return Article(
        source_id="arjay_blog",
        external_id=f"https://blog.arjaythedev.com/p/post-{n}",
        title=f"Post {n}",
        url=f"https://blog.arjaythedev.com/p/post-{n}",
        section=None,
        published_at=datetime(2026, 1, n, 12, 0, tzinfo=timezone.utc),
        byline="Arjay McCandless",
        body_text=f"Body of post {n}.",
        body_html=f"<p>Body of post {n}.</p>",
        word_count=4,
    )


def test_persistent_digest_filename_and_date_under_title(tmp_path: Path):
    articles = [_article(1), _article(2)]
    path = build_digest(
        articles,
        output_dir=tmp_path,
        source_name="The Dev Download",
        source_id="arjay_blog",
        filename="arjay-blog-archive.epub",
        persistent=True,
        date_under_title=True,
        groups=[("", articles)],
    )
    assert path.name == "arjay-blog-archive.epub"
    with zipfile.ZipFile(path) as zf:
        title = next(n for n in zf.namelist() if n.endswith("title.xhtml"))
        chap = next(n for n in zf.namelist() if n.endswith("chap_000.xhtml"))
        title_text = zf.read(title).decode()
        chap_text = zf.read(chap).decode()
    assert "The Dev Download" in title_text
    assert "Tuesday" not in title_text
    assert "2 articles" in title_text
    assert "<h1>Post 1</h1>" in chap_text
    assert "Jan 1, 2026" in chap_text
    assert "2026-01-01 12:00 UTC" not in chap_text


def test_prune_leaves_persistent_archive(tmp_path: Path):
    (tmp_path / "arjay-blog-archive.epub").write_bytes(b"archive")
    for day in range(10, 20):
        (tmp_path / f"digest-2026-08-{day}-guardian.epub").write_bytes(b"g")
    prune_digests(tmp_path, retention=3)
    assert (tmp_path / "arjay-blog-archive.epub").is_file()
    remaining = sorted(p.name for p in tmp_path.glob("digest-*.epub"))
    assert remaining == [
        "digest-2026-08-17-guardian.epub",
        "digest-2026-08-18-guardian.epub",
        "digest-2026-08-19-guardian.epub",
    ]


def test_allowed_filenames():
    assert is_allowed_epub_filename("digest-2026-08-18-guardian.epub")
    assert is_allowed_epub_filename("arjay-blog-archive.epub")
    assert not is_allowed_epub_filename("not-a-digest.epub")
    assert not is_allowed_epub_filename("../secret.epub")


async def test_archive_run_persists_bodies_and_writes_epub(client, data_dir: Path, monkeypatch):
    source = SOURCES["arjay_blog"]
    article = _article(3)
    stub = ArticleStub(
        source_id=article.source_id,
        external_id=article.external_id,
        title=article.title,
        url=article.url,
        published_at=article.published_at,
    )

    async def headlines(_config, _max_items, *, known_ok_ids=None):
        assert article.external_id not in (known_ok_ids or set())
        return [stub]

    async def fetch(_config, _stub):
        return article

    monkeypatch.setattr(source, "get_headlines", headlines)
    monkeypatch.setattr(source, "fetch_article", fetch)

    with Session(engine) as session:
        activate_source(session, "arjay_blog", active=True)
        run = Run(source_id="arjay_blog", status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    await execute_run(run_id)

    with Session(engine) as session:
        run = session.get(Run, run_id)
        posts = session.exec(select(SourcePost).where(SourcePost.source_id == "arjay_blog")).all()
        assert run is not None
        assert run.status == "success"
        assert run.articles_fetched == 1
        assert run.digest_filename == "arjay-blog-archive.epub"
        assert len(posts) == 1
        assert posts[0].body_text == "Body of post 3."
    assert (data_dir / "digests" / "arjay-blog-archive.epub").is_file()


async def test_archive_zero_new_is_success_and_rebuilds(client, data_dir: Path, monkeypatch):
    source = SOURCES["arjay_blog"]
    stored = _article(1)

    async def headlines(_config, _max_items, *, known_ok_ids=None):
        assert stored.external_id in (known_ok_ids or set())
        return []

    monkeypatch.setattr(source, "get_headlines", headlines)

    with Session(engine) as session:
        activate_source(session, "arjay_blog", active=True)
        session.add(
            SourcePost(
                source_id=stored.source_id,
                external_id=stored.external_id,
                title=stored.title,
                url=stored.url,
                published_at=stored.published_at,
                byline=stored.byline,
                body_text=stored.body_text,
                body_html=stored.body_html,
                fetch_status="ok",
                word_count=stored.word_count,
            )
        )
        run = Run(source_id="arjay_blog", status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    await execute_run(run_id)

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "success"
        assert run.articles_fetched == 0
        assert run.articles_failed == 0
        assert run.error_message is None
        assert run.digest_filename == "arjay-blog-archive.epub"
    assert (data_dir / "digests" / "arjay-blog-archive.epub").is_file()

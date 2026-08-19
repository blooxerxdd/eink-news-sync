from datetime import datetime, timezone
from pathlib import Path

from xml.etree.ElementTree import Element, SubElement, tostring

from config import DIGESTS_DIR, OPDS_FEED_LIMIT

ATOM = "http://www.w3.org/2005/Atom"


def list_digest_files(directory: Path | None = None) -> list[Path]:
    directory = directory or DIGESTS_DIR
    if not directory.exists():
        return []
    return sorted(directory.glob("digest-*.epub"), key=lambda p: p.name, reverse=True)


def digest_public_url(filename: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/download/{filename}"


def build_opds_feed(*, title: str, base_url: str, limit: int = OPDS_FEED_LIMIT) -> bytes:
    files = list_digest_files()[:limit]
    updated = (
        _file_mtime(files[0]).strftime("%Y-%m-%dT%H:%M:%SZ")
        if files
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    feed = Element("feed")
    feed.set("xmlns", ATOM)
    _el(feed, "id", f"{base_url.rstrip('/')}/opds")
    _el(feed, "title", title)
    _el(feed, "updated", updated)
    author = SubElement(feed, "author")
    _el(author, "name", "eink-news-sync")
    _link(feed, rel="self", href=f"{base_url.rstrip('/')}/opds", type="application/atom+xml;profile=opds-catalog;kind=acquisition")
    _link(feed, rel="start", href=f"{base_url.rstrip('/')}/opds", type="application/atom+xml;profile=opds-catalog;kind=acquisition")

    if not files:
        entry = SubElement(feed, "entry")
        _el(entry, "id", f"{base_url.rstrip('/')}/opds#empty")
        _el(entry, "title", "No digests yet")
        _el(entry, "updated", updated)
        _el(entry, "content", "No daily digest has been built yet. Trigger a sync from the web UI.")

    for path in files:
        mtime = _file_mtime(path)
        stamp = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
        display_date = path.stem.replace("digest-", "")
        entry = SubElement(feed, "entry")
        _el(entry, "id", f"urn:eink-news-sync:{path.name}")
        _el(entry, "title", f"Daily Digest — {display_date}")
        _el(entry, "updated", stamp)
        _el(entry, "published", stamp)
        summary = SubElement(entry, "summary")
        summary.text = f"EPUB digest ({_size_label(path.stat().st_size)})"
        _link(
            entry,
            rel="http://opds-spec.org/acquisition",
            href=digest_public_url(path.name, base_url),
            type="application/epub+zip",
        )
        _link(
            entry,
            rel="alternate",
            href=digest_public_url(path.name, base_url),
            type="application/epub+zip",
        )

    xml = tostring(feed, encoding="utf-8", xml_declaration=True)
    return xml


def _el(parent: Element, tag: str, text: str) -> Element:
    child = SubElement(parent, tag)
    child.text = text
    return child


def _link(parent: Element, rel: str, href: str, type: str) -> Element:
    child = SubElement(parent, "link")
    child.set("rel", rel)
    child.set("href", href)
    child.set("type", type)
    return child


def _file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _size_label(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"

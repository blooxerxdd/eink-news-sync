from sources.base import Article

OTHER_SECTION = "Other"


def group_articles_by_section(
    articles: list[Article],
    section_order: list[str] | None = None,
) -> list[tuple[str, list[Article]]]:
    """Group articles for a single EPUB: configured section order, then A–Z, then Other.

    Within each group, newest ``published_at`` first, then title.
    Articles with no section are labeled Other. If nothing has a section, returns
    one unlabeled group (flat TOC, no divider pages).
    """
    if not articles:
        return []

    buckets: dict[str, list[Article]] = {}
    labels: dict[str, str] = {}
    for article in articles:
        key = _group_key(article)
        buckets.setdefault(key, []).append(article)
        if key not in labels:
            labels[key] = _group_label(article, key)

    for items in buckets.values():
        items.sort(key=_within_section_sort)

    if not any(key for key in buckets):
        return [("", buckets[""])]

    result: list[tuple[str, list[Article]]] = []
    seen: set[str] = set()
    for raw in section_order or []:
        key = raw.strip().lower()
        if not key or key in seen or key not in buckets:
            continue
        result.append((labels[key], buckets[key]))
        seen.add(key)

    leftover = sorted(
        (key for key in buckets if key and key not in seen),
        key=lambda k: labels[k].casefold(),
    )
    for key in leftover:
        result.append((labels[key], buckets[key]))

    if "" in buckets:
        result.append((OTHER_SECTION, buckets[""]))
    return result


def _group_key(article: Article) -> str:
    if article.section_id and article.section_id.strip():
        return article.section_id.strip().lower()
    if article.section and article.section.strip():
        return article.section.strip().lower()
    return ""


def _group_label(article: Article, key: str) -> str:
    if article.section and article.section.strip():
        return article.section.strip()
    if article.section_id and article.section_id.strip():
        return article.section_id.strip()
    return OTHER_SECTION if not key else key


def _within_section_sort(article: Article) -> tuple[float, str]:
    published = article.published_at.timestamp() if article.published_at else 0.0
    return (-published, article.title.casefold())

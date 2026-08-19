from sources.base import NewsSource
from sources.guardian import GuardianSource

SOURCES: dict[str, NewsSource] = {
    "guardian": GuardianSource(),
}


def get_source(source_id: str) -> NewsSource:
    try:
        return SOURCES[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown source: {source_id}") from exc

from html.parser import HTMLParser
import re
from html import escape as html_escape


ALLOWED_TAGS = {
    "p",
    "h2",
    "h3",
    "h4",
    "blockquote",
    "em",
    "strong",
    "i",
    "b",
    "a",
    "ul",
    "ol",
    "li",
    "br",
    "span",
}
ALLOWED_ATTRS = {"a": {"href", "title"}}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._parts)).strip()


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_TAGS:
            return
        allowed = ALLOWED_ATTRS.get(tag, set())
        attr_str = ""
        for name, value in attrs:
            if name in allowed and value:
                attr_str += f' {name}="{html_escape(value, quote=True)}"'
        if tag == "br":
            self._out.append("<br/>")
            return
        self._out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in ALLOWED_TAGS and tag != "br":
            self._out.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._out.append("<br/>")
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        self._out.append(html_escape(data, quote=False))

    def get_html(self) -> str:
        return "".join(self._out)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return parser.get_text()


def sanitize_html(html: str) -> str:
    parser = _Sanitizer()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return f"<p>{html_escape(html_to_text(html))}</p>"
    cleaned = parser.get_html().strip()
    return cleaned or f"<p>{html_escape(html_to_text(html))}</p>"


def text_to_html_paragraphs(text: str) -> str:
    chunks = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not chunks:
        return "<p></p>"
    return "".join(f"<p>{html_escape(chunk)}</p>" for chunk in chunks)

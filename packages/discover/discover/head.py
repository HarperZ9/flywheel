"""Read the parts of an HTML page that search and link previews use."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class Page:
    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    canonical: str = ""
    ld_blocks: list[str] = field(default_factory=list)
    has_video: bool = False
    refresh: bool = False

    @property
    def noindex(self) -> bool:
        return "noindex" in self.meta.get("robots", "").lower()

    def ld_types(self) -> tuple[set[str], list[str], list[dict]]:
        """Every @type in the JSON-LD blocks, parse errors, and the typed nodes."""
        types: set[str] = set()
        errors: list[str] = []
        nodes: list[dict] = []
        for block in self.ld_blocks:
            try:
                data = json.loads(block)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            _walk(data, types, nodes)
        return types, errors, nodes


def _walk(data: object, types: set[str], nodes: list[dict]) -> None:
    if isinstance(data, list):
        for item in data:
            _walk(item, types, nodes)
    elif isinstance(data, dict):
        kind = data.get("@type")
        for name in kind if isinstance(kind, list) else [kind]:
            if isinstance(name, str):
                types.add(name)
                nodes.append(data)
        for value in data.values():
            if isinstance(value, (dict, list)):
                _walk(value, types, nodes)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page()
        self._in_title = False
        self._in_ld = False
        self._buf: list[str] = []
        self._video_controls = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title" and not self.page.title:
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key and key not in self.page.meta:
                self.page.meta[key] = a.get("content", "")
            if a.get("http-equiv", "").lower() == "refresh":
                self.page.refresh = True
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.page.canonical = self.page.canonical or a.get("href", "")
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_ld, self._buf = True, []
        elif tag == "video":
            # A watchable video: it has controls and a source. A muted decorative
            # loop without controls is not the page's content and needs no markup.
            self._video_controls = "controls" in a
            if self._video_controls and a.get("src"):
                self.page.has_video = True
        elif tag == "source" and self._video_controls and a.get("src"):
            self.page.has_video = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "video":
            self._video_controls = False
        elif tag == "script" and self._in_ld:
            self._in_ld = False
            self.page.ld_blocks.append("".join(self._buf))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page.title += data
        elif self._in_ld:
            self._buf.append(data)


def read(source: str) -> Page:
    parser = _Parser()
    parser.feed(source)
    parser.page.title = " ".join(parser.page.title.split())
    return parser.page

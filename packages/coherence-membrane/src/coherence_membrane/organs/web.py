"""WebDocumentOrgan -- the membrane's web sense: perceiving a live web page as
witnessed *structure*, not a screenshot.

Sight perceives pixels and hearing perceives sound; this perceives a WEB
DOCUMENT -- the served HTML the operator fetched -- reduced to title, headings,
links, and whitespace-normalised visible text, each stamped with the identity
digest of the exact bytes received. It is the construction-over-detection answer
to the screenshot loop: a re-derivable structural reading rather than a pixel
buffer hoped-correct.

Inert and fail-closed like every organ: it issues a single HTTP ``GET`` (it
observes external state; it never POSTs, mutates, or executes), and any fetch or
parse failure yields identity-only + ``UNVERIFIED`` -- never a crash and never
fabricated structure. ``Status`` is advisory; there is no authority-shaped value.

Boundaries, stated honestly:
  * v0 perceives the *served* HTML only. JavaScript-rendered DOM, network-trace
    capture, and rendered-region geometry are named later increments, not faked.
  * Stdlib only -- ``urllib`` + ``html.parser``. No browser and no third-party
    parser in the trust path.
  * It does NOT import the quarantined ``behavior-transform.io`` ``safe_fetch``;
    the accountable web sense keeps its own clean fetch so it never depends on
    the adversarial IO membrane.
  * Only ``http``/``https`` are fetched; any other scheme (``file:``, ``ftp:``,
    …) is rejected to ``UNVERIFIED`` and never read.
  * Network I/O lives only in ``fetch_url``; ``perceive_html`` and ``selftest``
    are pure and offline, so the perception logic is deterministically testable
    without touching the network.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult

_URL_RE = re.compile(r"^(https?)://", re.IGNORECASE)
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_SUPPRESS = {"script", "style", "noscript", "template"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

_SELFTEST_HTML = (
    b"<!doctype html><html><head><title>Hello Frontier</title>"
    b'<meta name="description" content="a test page"></head>'
    b"<body><h1>Main</h1><h2>Sub</h2>"
    b"<p>Some visible text here.</p>"
    b'<a href="https://example.com/a">A</a><a href="/b">B</a>'
    b"<script>var ignored = 1;</script>"
    b"</body></html>"
)


def _normalize_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


class _HtmlExtract(HTMLParser):
    """Lenient, inert HTML reader: collects title, meta description, headings,
    links, and visible text. It never evaluates anything; script/style text is
    suppressed rather than perceived as visible content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta_description: str | None = None
        self.headings: list[str] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self.links: list[str] = []
        self.text_parts: list[str] = []
        self._suppress_depth = 0

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag in _SUPPRESS:
            self._suppress_depth += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            if attr.get("name", "").lower() == "description" and attr.get("content"):
                self.meta_description = attr["content"]
        elif tag == "a":
            href = attr.get("href")
            if href:
                self.links.append(href)
        elif tag in _HEADINGS:
            self._heading_tag = tag
            self._heading_parts = []

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in _SUPPRESS:
            if self._suppress_depth > 0:
                self._suppress_depth -= 1
        elif tag == "title":
            self.in_title = False
        elif self._heading_tag is not None and tag == self._heading_tag:
            text = _normalize_ws("".join(self._heading_parts))
            if text:
                self.headings.append(text)
            self._heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str):
        if self._suppress_depth > 0:
            return
        if self.in_title:
            self.title_parts.append(data)
            return
        if self._heading_tag is not None:
            self._heading_parts.append(data)
        if data.strip():
            self.text_parts.append(data)


def _looks_like_html(text: str) -> bool:
    head = text[:8192].lower()
    return any(
        marker in head
        for marker in ("<!doctype html", "<html", "<head", "<body", "</a>", "<p>", "<p ", "<div")
    )


def perceive_html(
    payload: bytes,
    source: str,
    *,
    command: str | None = None,
    http_meta: dict | None = None,
) -> Observation:
    """Pure, offline perception of served HTML bytes into one witnessed
    Observation. Non-HTML or undecodable input degrades to identity-only +
    UNVERIFIED; it never crashes and never fabricates structure."""
    identity = sha256_hex(payload)
    data: dict = {"identity_sha256": identity, "bytes": len(payload)}
    if http_meta:
        for key in ("http_status", "content_type", "final_url"):
            if key in http_meta:
                data[key] = http_meta[key]

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("latin-1", errors="replace")

    if not _looks_like_html(text):
        data.update({
            "format": "unknown",
            "decoded": False,
            "title": None,
            "headings": [],
            "link_count": 0,
            "links": [],
            "text_len": 0,
            "canonical_text_sha256": None,
            "meta_description": None,
            "visible_text_sample": "",
        })
        return Observation(
            organ="web-document",
            subject=source,
            summary="not a perceivable web document (identity only)",
            status=Status.UNVERIFIED,
            provenance=Provenance.witness_bytes(source, payload, "low", command=command),
            data=data,
        )

    parser = _HtmlExtract()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # HTMLParser is lenient, but never crash the organ
        data.update({
            "format": "unknown",
            "decoded": False,
            "title": None,
            "headings": [],
            "link_count": 0,
            "links": [],
            "text_len": 0,
            "canonical_text_sha256": None,
            "meta_description": None,
            "visible_text_sample": "",
            "parse_note": str(exc),
        })
        return Observation(
            organ="web-document",
            subject=source,
            summary="web document unparseable (identity only)",
            status=Status.UNVERIFIED,
            provenance=Provenance.witness_bytes(source, payload, "low", command=command),
            data=data,
        )

    title = _normalize_ws("".join(parser.title_parts)) or None
    visible = _normalize_ws(" ".join(parser.text_parts))
    canonical_text_sha = sha256_hex(visible.encode("utf-8")) if visible else None
    data.update({
        "format": "html",
        "decoded": True,
        "title": title,
        "headings": parser.headings,
        "link_count": len(parser.links),
        "links": parser.links[:100],
        "text_len": len(visible),
        "canonical_text_sha256": canonical_text_sha,
        "meta_description": parser.meta_description,
        "visible_text_sample": visible[:280],
    })
    return Observation(
        organ="web-document",
        subject=source,
        summary=f"web document perceived ({len(parser.links)} links, {len(visible)} text chars)",
        status=Status.PASS,
        provenance=Provenance.witness_bytes(source, payload, "high", command=command),
        data=data,
    )


def fetch_url(
    url: str,
    *,
    timeout: float = 10.0,
    max_bytes: int = 5_000_000,
) -> tuple[bytes, dict]:
    """Stdlib http/https GET. Returns (payload, meta). Raises on any error or on
    a non-http(s) scheme; callers degrade to UNVERIFIED rather than propagate."""
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"unsupported scheme: {scheme!r}")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "coherence-membrane-web-organ/0 (+inert observer)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (scheme checked)
        payload = response.read(max_bytes + 1)[:max_bytes]
        status = getattr(response, "status", None) or response.getcode()
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
    return payload, {
        "http_status": int(status),
        "content_type": content_type,
        "final_url": final_url,
        "bytes": len(payload),
    }


class WebDocumentOrgan:
    """Inert web sense. ``observe`` accepts a URL (fetched), raw bytes, or a path
    to a saved document. Network I/O is confined to ``fetch_url``; everything
    else is offline and pure."""

    name = "web-document"

    def observe(self, subject) -> list[Observation]:
        if isinstance(subject, (bytes, bytearray)):
            return [perceive_html(bytes(subject), "<bytes>")]
        if isinstance(subject, str):
            if _URL_RE.match(subject):
                try:
                    payload, meta = fetch_url(subject)
                except Exception as exc:  # network/HTTP/scheme failure -> fail closed
                    return [self._unreadable(subject, str(exc))]
                return [
                    perceive_html(
                        payload,
                        meta.get("final_url", subject),
                        command=f"GET {subject}",
                        http_meta=meta,
                    )
                ]
            if _SCHEME_RE.match(subject):
                return [self._unreadable(subject, "non-http scheme rejected")]
            # otherwise treat as a local path to a saved document
            try:
                path = Path(subject)
                payload = path.read_bytes()
            except (OSError, ValueError) as exc:
                return [self._unreadable(str(subject)[:64], str(exc))]
            return [perceive_html(payload, str(path))]
        return [self._unreadable(repr(subject)[:64], "unsupported subject type")]

    def _unreadable(self, source: str, note: str) -> Observation:
        return Observation(
            organ=self.name,
            subject=source,
            summary="web subject unreadable",
            status=Status.UNVERIFIED,
            provenance=Provenance.witness_bytes(source, b"", "low"),
            data={
                "format": "unknown",
                "decoded": False,
                "title": None,
                "identity_sha256": sha256_hex(b""),
                "note": note,
            },
        )

    # --- selftest -------------------------------------------------------------

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        ob = perceive_html(_SELFTEST_HTML, "selftest://doc")
        rederived = sha256_hex(_SELFTEST_HTML)

        checks.append(Check("title extracted", ob.data.get("title") == "Hello Frontier"))
        checks.append(Check("links counted", ob.data.get("link_count") == 2))
        checks.append(Check(
            "absolute link captured",
            "https://example.com/a" in ob.data.get("links", []),
        ))
        checks.append(Check("heading extracted", "Main" in ob.data.get("headings", [])))
        checks.append(Check("meta description read", ob.data.get("meta_description") == "a test page"))
        checks.append(Check("identity re-derives", ob.data.get("identity_sha256") == rederived))
        checks.append(Check(
            "provenance digest full-width",
            ob.provenance.digest == "sha256:" + rederived and len(rederived) == 64,
        ))
        checks.append(Check(
            "canonical text stable",
            ob.data.get("canonical_text_sha256")
            == perceive_html(_SELFTEST_HTML, "selftest://doc").data.get("canonical_text_sha256"),
        ))
        checks.append(Check(
            "script text not perceived as visible",
            "ignored" not in ob.data.get("visible_text_sample", ""),
        ))
        non_html = perceive_html(b"\x00\x01\x02\x03", "selftest://bin")
        checks.append(Check(
            "non-html fails closed",
            non_html.status == Status.UNVERIFIED and non_html.data.get("title") is None,
        ))
        checks.append(Check(
            "status is advisory (not authority)",
            ob.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                          Status.NEEDS_HUMAN, Status.BLOCK},
        ))
        return SelftestResult(self.name, checks)

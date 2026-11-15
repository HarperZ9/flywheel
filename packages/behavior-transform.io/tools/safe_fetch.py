#!/usr/bin/env python3
"""Fetch an external URL.

Use this wrapper when an operator or agent needs a URL body with
predictable timeout, redirect, size-cap, cache, and metadata behavior.

Usage
-----
    python tools/safe_fetch.py <url>                  # full fetch to stdout
    python tools/safe_fetch.py <url> --to-cache       # write .warden-safe-cache/<hash>.safe
    python tools/safe_fetch.py <url> --text-only      # strip HTML before output
    python tools/safe_fetch.py <url> --summary        # structural summary only
    python tools/safe_fetch.py <url> --hash           # SHA-256 + metadata only
    python tools/safe_fetch.py <url> --diff-only      # audit counters only
    python tools/safe_fetch.py <url> --headers        # include response headers
    python tools/safe_fetch.py <url> --max-bytes N    # cap body size (default: 2 MiB)

Non-destructive - never writes to the URL's source. Archives the native
response under .warden-safe-cache/
for auditing unless --no-archive is given.

Network policy:
    * Default 20-second connect+read timeout.
    * One redirect hop max (configurable via --max-redirects).
    * Refuses non-HTTP(S) schemes (file://, ftp://, data:, javascript:).
    * Respects HTTPS certificate verification (cannot be disabled here --
      use a real client for that).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from io_state import add_io_toggle_args, transforms_enabled
from _core import build_engine


_DEFAULT_TIMEOUT_S = 20.0
_DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB
_DEFAULT_UA = "warden-safe-fetch/0.1 (+stdlib-urllib; auditing-only)"
_ALLOWED_SCHEMES = {"http", "https"}


class _PlainTextExtractor(HTMLParser):
    """Minimal HTML-to-text extractor. Drops script/style content."""

    _SKIP_TAGS = {"script", "style", "noscript", "iframe", "object", "embed"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag.lower() in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        joined = "".join(self._chunks)
        # Collapse runs of whitespace inside lines; preserve paragraph breaks.
        lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in joined.splitlines()]
        # Drop empty lines at start/end; collapse multi-blank to single blank.
        out: list[str] = []
        prev_blank = False
        for line in lines:
            if line == "":
                if not prev_blank:
                    out.append("")
                prev_blank = True
            else:
                out.append(line)
                prev_blank = False
        while out and out[0] == "":
            out.pop(0)
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out)


def _strip_html(body: str) -> str:
    parser = _PlainTextExtractor()
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        # If the HTML parser explodes, fall back to a naive tag strip.
        return re.sub(r"<[^>]+>", " ", body)
    return parser.text()


def _fetch(
    url: str,
    *,
    timeout_s: float,
    max_bytes: int,
    max_redirects: int,
    user_agent: str,
) -> tuple[bytes, dict, str]:
    """Return (body_bytes, headers_dict, final_url)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"refusing scheme: {parsed.scheme!r} "
            f"(only http/https are permitted by safe_fetch)"
        )

    class _LimitedRedirect(urllib.request.HTTPRedirectHandler):
        max_redirections = max_redirects

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            # Disallow redirects to non-http(s) schemes (e.g. javascript:).
            np = urllib.parse.urlparse(newurl)
            if np.scheme.lower() not in _ALLOWED_SCHEMES:
                raise urllib.error.HTTPError(
                    newurl, code, f"redirect to disallowed scheme: {np.scheme!r}",
                    headers, fp,
                )
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        _LimitedRedirect(),
        urllib.request.HTTPSHandler(context=ctx),
    )
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with opener.open(req, timeout=timeout_s) as resp:
        # Read up to max_bytes + 1 so we can detect truncation.
        body = resp.read(max_bytes + 1)
        truncated = len(body) > max_bytes
        if truncated:
            body = body[:max_bytes]
        hdrs = {k: v for k, v in resp.headers.items()}
        if truncated:
            hdrs["x-warden-truncated"] = f"true; cap={max_bytes}"
        return body, hdrs, resp.geturl()


def _decode(body: bytes, headers: dict) -> str:
    ctype = headers.get("Content-Type", "") or headers.get("content-type", "")
    enc = "utf-8"
    m = re.search(r"charset=([\w\-]+)", ctype, flags=re.IGNORECASE)
    if m:
        enc = m.group(1)
    try:
        return body.decode(enc, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _cache_path(url: str, suffix: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    base = Path.cwd() / ".warden-safe-cache" / "fetch"
    return base / f"{digest}{suffix}"


def _summary(text: str, url: str, final_url: str) -> dict:
    line_count = text.count("\n") + (0 if text.endswith("\n") else 1 if text else 0)
    byte_len = len(text.encode("utf-8"))
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    return {
        "url": url,
        "final_url": final_url,
        "line_count": line_count,
        "byte_length": byte_len,
        "sha256_prefix": sha,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch an external URL through the selected IO mode "
            "(network companion to safe_read)."
        )
    )
    parser.add_argument("url", type=str)
    parser.add_argument(
        "--to-cache",
        action="store_true",
        help="Write body to .warden-safe-cache/fetch/<hash>.safe instead of stdout.",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Strip HTML to plain text before output.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit structural summary only (line/byte count, sha prefix, audit counts).",
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        help="Emit SHA-256 prefix + metadata only.",
    )
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Emit audit counters only.",
    )
    parser.add_argument(
        "--headers",
        action="store_true",
        help="Include response headers in the output payload.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=_DEFAULT_MAX_BYTES,
        help=f"Cap response body bytes (default: {_DEFAULT_MAX_BYTES}).",
    )
    parser.add_argument(
        "--max-redirects",
        type=int,
        default=1,
        help="Maximum redirect hops (default: 1).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_DEFAULT_TIMEOUT_S,
        help=f"Connect+read timeout in seconds (default: {_DEFAULT_TIMEOUT_S}).",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default=_DEFAULT_UA,
        help="User-Agent header for the request.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not archive the native response under .warden-safe-cache/fetch/.",
    )
    add_io_toggle_args(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        body_bytes, headers, final_url = _fetch(
            args.url,
            timeout_s=args.timeout,
            max_bytes=args.max_bytes,
            max_redirects=args.max_redirects,
            user_agent=args.user_agent,
        )
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"safe_fetch: HTTP error {e.code} for {args.url}: {e.reason}\n")
        return 3
    except urllib.error.URLError as e:
        sys.stderr.write(f"safe_fetch: URL error for {args.url}: {e.reason}\n")
        return 3
    except (ssl.SSLError, ValueError, TimeoutError) as e:
        sys.stderr.write(f"safe_fetch: {type(e).__name__} for {args.url}: {e}\n")
        return 3

    if not args.no_archive:
        raw_path = _cache_path(args.url, ".raw")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(body_bytes)

    raw_text = _decode(body_bytes, headers)
    if args.text_only:
        raw_text = _strip_html(raw_text)

    if args.hash:
        out = _summary(raw_text, args.url, final_url)
        sys.stdout.write(json.dumps({"hash_only": out}, indent=2) + "\n")
        return 0

    io_on = transforms_enabled(args)
    if io_on:
        engine = build_engine()
        payload_text, t1_hits, t2_hits = engine.apply(raw_text)
        counter = {"tier1": t1_hits, "tier2": t2_hits}
    else:
        payload_text, counter = raw_text, {"tier1": 0, "tier2": 0}
    counts = {tier: int(n) for tier, n in counter.items()}
    total = sum(counts.values())

    if args.diff_only:
        sys.stdout.write(
            json.dumps(
                {
                    "url": args.url,
                    "final_url": final_url,
                    "audit_counts": counts,
                    "total": total,
                    "io_channel": "on" if io_on else "off",
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    if args.summary:
        summary = _summary(payload_text, args.url, final_url)
        summary["content_type"] = headers.get("Content-Type", "")
        summary["truncated"] = "x-warden-truncated" in headers
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        return 0

    if not io_on:
        payload = raw_text
        if args.to_cache:
            dest = _cache_path(args.url, ".safe")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(payload, encoding="utf-8")
            sys.stderr.write(f"wrote: {dest}\n")
            return 0
        sys.stdout.write(payload)
        if payload and not payload.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    payload = payload_text
    if args.headers:
        header_block_lines = ["# ---- response headers ----"]
        for k, v in headers.items():
            header_block_lines.append(f"# {k}: {v}")
        payload = "\n".join(header_block_lines) + "\n\n" + payload

    if args.to_cache:
        dest = _cache_path(args.url, ".safe")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload, encoding="utf-8")
        sys.stderr.write(f"wrote: {dest}\n")
        return 0

    # Reconfigure stdout to UTF-8 — same defensive shape as safe_read.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    try:
        sys.stdout.write(payload)
    except UnicodeEncodeError:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(payload.encode("utf-8", errors="replace"))
        else:
            sys.stdout.write(payload.encode("ascii", errors="replace").decode("ascii"))
    if not payload.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

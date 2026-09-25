"""check_tracked_junit.py -- no tracked JUnit report names a machine or a local path.

pytest writes the build machine's hostname into every JUnit report, and a
report of a failed import or a failed assertion carries the traceback's
absolute paths, user profile included. Until 2026-09-23 the pytest oracle
wrote `_oracle_junit.xml` into every task workdir, and 1149 of those reports
were committed under artifacts/, tasks/ and .flywheel-run/. Every one named the
build host, and 63 named absolute paths on it. None was read by the oracle
after PR #288, and no receipt pinned their bytes, so they were removed. See
project-docs/records/2026-09-23-oracle-junit-untrack.md.

The .gitignore now keeps `_oracle_junit.xml` and the per-run
`_oracle_junit_<nonce>.xml` out of `git add`. This gate catches what the ignore
file cannot: a report added with `git add -f`, and a JUnit report written under
another name or extension.

The gate reads every blob git tracks, not the files on disk. A blob is a JUnit
report when its path has the oracle's file name (starts with `_oracle_junit`
and ends in `.xml`, the rule in harness/junit_report.py, `is_report_name`), or
when its root element is `<testsuites>` or `<testsuite>`, whatever the file is
called. Before the root it skips a byte order mark, whitespace, the XML
declaration, processing instructions, comments and a DOCTYPE. It reads UTF-8,
UTF-16 or UTF-32 that opens with a byte order mark, and UTF-16 without one.

A report fails when a start tag has a non-empty `hostname` attribute, in any
XML spelling (`hostname="h"`, `hostname = 'h'`), or when any of its text looks
like an absolute path: a drive path (`C:\\` or `C:/`), a UNC path
(`\\\\host\\share`), or a POSIX path under a machine root such as `/home/`,
`/Users/`, `/tmp/`, `/usr/`, `/data/`, `/cygdrive/`, `/workspaces/` or
`/__w/`. An MSYS2 drive root counts when a whole directory name follows it:
`/c/Users/` fails, and `/a/b` passes. The path rule errs toward failing. It
cannot tell a path on the build machine from a path-shaped literal in a test's
source, so a failure message quoting `'/tmp/cache'` or `'k:\\tv'` fails too.
A `hostname=` inside failure text is test data, not the attribute pytest
writes, and passes. Nothing is grandfathered.

Exit 0 clean, 1 at least one report names a host or an absolute path, 2 git
cannot list or read the tracked files, a tracked path is not valid UTF-8, or
the tree tracks nothing. A broken checkout never reads as clean.

Does not prove: the tree names no machine. The gate reads JUnit reports only.
Receipts that quote pytest's stdout, such as the `rootdir:` line, still carry
absolute paths. These also pass: a host or user name held in any other
attribute or in text, a POSIX path under a root not listed here, a report too
malformed for its start tags to parse, a compressed report, and UTF-32 without
a byte order mark.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import IO

_REPORT_PREFIX = "_oracle_junit"   # harness/junit_report.py, _PREFIX
_BOMS = (   # leading bytes, the codec they announce, how many bytes to drop
    (b"\xff\xfe\x00\x00", "utf-32-le", 4), (b"\x00\x00\xfe\xff", "utf-32-be", 4),
    (b"\xff\xfe", "utf-16-le", 2), (b"\xfe\xff", "utf-16-be", 2),
)
# Each prolog node is matched by a pattern that cannot run past its own end,
# so a file that is not a report fails the match in linear time.
_PROLOG = (rb"(?:\s"
           rb"|<\?[^?]*(?:\?(?!>)[^?]*)*\?>"              # declaration, PI
           rb"|<!--[^-]*(?:-(?!->)[^-]*)*-->"             # comment
           rb"|<!DOCTYPE[^>\[]*(?:\[[^\]]*\][^>]*)?>"     # DOCTYPE
           rb")*")
_JUNIT_ROOT = re.compile(rb"\A(?:\xef\xbb\xbf)?" + _PROLOG + rb"<testsuites?[\s>/]")
_START_TAG = re.compile(
    rb"""<[A-Za-z_][^\s/>]*((?:\s+[^\s=/>]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*/?>""")
_ATTR = re.compile(rb"""([^\s=/>]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_ABSOLUTE = (
    re.compile(rb"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'<>]*"),
    re.compile(rb"(?<!\\)\\\\[A-Za-z0-9._$-]+\\[^\s\"'<>]*"),
    # An MSYS2 drive root such as /c/ counts only when a directory name of two
    # or more characters and a slash follow it, so a URL path literal such as
    # '/a/b' in a test's source does not read as one.
    re.compile(rb"(?<![\w.~-])/(?:(?:home|Users|root|tmp|private|var|mnt|opt|"
               rb"srv|Volumes|runner|github|workspaces?|builds|usr|cygdrive|__w|"
               rb"data)/|[A-Za-z]/[^\s\"'<>/]{2,}/)[^\s\"'<>]*"),
)
_SHOWN = 3   # absolute paths printed per report; the rest are counted


def tracked_blobs(root: Path) -> list[tuple[str, str]]:
    """(path, blob id) for every regular file git tracks under root."""
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "-s", "-z"],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files failed in {root}: {detail}")
    rows = []
    for rec in proc.stdout.split(b"\0"):
        if not rec:
            continue
        meta, raw = rec.split(b"\t", 1)
        mode, blob = meta.split()[:2]
        if mode in (b"100644", b"100755"):
            rows.append((_decode_path(raw), blob.decode("ascii")))
    return rows


def _decode_path(raw: bytes) -> str:
    """One path from `git ls-files -z`, or RuntimeError if it is not UTF-8."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"tracked path is not valid UTF-8: {raw!r}") from exc


def read_blobs(root: Path, blobs: list[str],
               keep: Callable[[str, bytes], bool]) -> dict[str, bytes]:
    """The bytes of each blob that keep(blob id, bytes) accepts.

    One `git cat-file --batch` call streams every blob, and only the kept ones
    stay in memory, so reading the whole tree costs one pass and little memory.
    """
    if not blobs:
        return {}
    with tempfile.TemporaryFile() as ids, tempfile.TemporaryFile() as err:
        ids.write("\n".join(blobs).encode("ascii") + b"\n")
        ids.seek(0)
        proc = subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"],
                                stdin=ids, stdout=subprocess.PIPE, stderr=err)
        try:
            data = _read_batch(proc.stdout, len(blobs), keep)
        finally:
            proc.stdout.close()
            code = proc.wait()
        err.seek(0)
        detail = err.read().decode("utf-8", errors="replace").strip()
    if code != 0:
        raise RuntimeError(f"git cat-file failed in {root}: {detail}")
    return data


def _read_batch(stream: IO[bytes], count: int,
                keep: Callable[[str, bytes], bool]) -> dict[str, bytes]:
    """Parse `git cat-file --batch` output: a header line, the body, a newline."""
    data = {}
    for _ in range(count):
        header = stream.readline().split()
        if len(header) != 3:
            raise RuntimeError(f"git cat-file could not read {header!r}")
        size = int(header[2])
        body = stream.read(size)
        if len(body) != size or stream.read(1) != b"\n":
            raise RuntimeError(f"git cat-file output ended inside {header[0]!r}")
        blob = header[0].decode("ascii")
        if keep(blob, body):
            data[blob] = body
    return data


def as_utf8(data: bytes) -> bytes:
    """The bytes re-encoded as UTF-8 when they are UTF-16 or UTF-32.

    A byte order mark names the codec. UTF-16 without one is recognised by a
    NUL in every other byte of its first four, as XML's own sniffing does.
    """
    for mark, codec, drop in _BOMS:
        if data.startswith(mark):
            return data[drop:].decode(codec, errors="replace").encode("utf-8")
    head = data[:4]
    if len(head) == 4 and head[1] == head[3] == 0 and head[0] and head[2]:
        return data.decode("utf-16-le", errors="replace").encode("utf-8")
    if len(head) == 4 and head[0] == head[2] == 0 and head[1] and head[3]:
        return data.decode("utf-16-be", errors="replace").encode("utf-8")
    return data


def is_report_name(path: str) -> bool:
    """The oracle's file name rule, copied from harness/junit_report.py."""
    name = path.rsplit("/", 1)[-1]
    return name.startswith(_REPORT_PREFIX) and name.endswith(".xml")


def is_junit_body(data: bytes) -> bool:
    """True when the root element, after any prolog, is a JUnit suite."""
    return bool(_JUNIT_ROOT.match(as_utf8(data)))


def is_junit_report(path: str, data: bytes) -> bool:
    """True for an oracle report by name, or any file whose root is a JUnit suite."""
    return is_report_name(path) or is_junit_body(data)


def _hostnames(data: bytes) -> list[str]:
    """Each non-empty `hostname` attribute value, read from start tags only."""
    hosts: list[str] = []
    for tag in _START_TAG.finditer(data):
        for name, double, single in _ATTR.findall(tag.group(1)):
            host = (double or single).decode("utf-8", "replace").strip()
            if name.rsplit(b":", 1)[-1] == b"hostname" and host \
                    and host not in hosts:
                hosts.append(host)
    return hosts


def findings(data: bytes) -> list[str]:
    """Each hostname a report names, then the absolute paths it holds."""
    data = as_utf8(data)
    out = [f"hostname {host}" for host in _hostnames(data)]
    paths: list[str] = []
    for pattern in _ABSOLUTE:
        for match in pattern.findall(data):
            text = match.decode("utf-8", "replace")
            if text not in paths:
                paths.append(text)
    out += [f"absolute path {p}" for p in paths[:_SHOWN]]
    if len(paths) > _SHOWN:
        out.append(f"and {len(paths) - _SHOWN} more absolute paths")
    return out


def reports(root: Path) -> list[tuple[str, bytes]]:
    """(path, bytes) for every tracked JUnit report under root."""
    rows = tracked_blobs(root)
    if not rows:
        raise RuntimeError(f"no tracked files in {root}")
    named = {blob for path, blob in rows if is_report_name(path)}
    data = read_blobs(root, sorted({blob for _, blob in rows}),
                      lambda blob, body: blob in named or is_junit_body(body))
    return [(p, data[b]) for p, b in rows
            if b in data and is_junit_report(p, data[b])]


def main(root: Path | None = None) -> int:
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    try:
        found = reports(root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"junit report gate could not read the tracked files: {exc}")
        return 2
    failed = 0
    for path, data in found:
        hits = findings(data)
        failed += bool(hits)
        for hit in hits:
            print(f"{path}: {hit}")
    if failed:
        print(f"{failed} of {len(found)} tracked JUnit reports name a host or "
              "an absolute path. Remove them with git rm; the oracle never "
              "reads a committed report.")
        return 1
    print(f"junit report gate clean: {len(found)} tracked JUnit reports, none "
          "names a host or an absolute path")
    return 0


if __name__ == "__main__":
    sys.exit(main())

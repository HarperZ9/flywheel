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
any other name.

A tracked file is a JUnit report when its name ends in `.xml` and either starts
with `_oracle_junit` (the rule in harness/junit_report.py, `is_report_name`) or
its root element is `<testsuites>` or `<testsuite>`. The gate reads the blob
git tracks, not the file on disk. A report fails when it has a non-empty
`hostname` attribute, or an absolute path: a drive path (`C:\\` or `C:/`), a UNC
path (`\\\\host\\share`), or a POSIX path under a machine root such as `/home/`,
`/Users/`, `/tmp/` or `/runner/`. A report with `hostname=""` and only
relative paths passes. Nothing is grandfathered.

Exit 0 clean, 1 at least one report names a host or an absolute path, 2 git
cannot list or read the tracked files, a tracked path is not valid UTF-8, or
the tree tracks nothing. A broken checkout never reads as clean.

Does not prove: the tree names no machine. The gate reads JUnit reports only.
Receipts that quote pytest's stdout, such as the `rootdir:` line, still carry
absolute paths, and a hostname or a user name held in any other attribute, or
a POSIX path under a root not listed here, passes.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPORT_PREFIX = "_oracle_junit"   # harness/junit_report.py, _PREFIX
_JUNIT_ROOT = re.compile(
    rb"\A(?:\xef\xbb\xbf)?\s*(?:<\?xml[^>]*\?>\s*)?(?:<!--.*?-->\s*)*"
    rb"<testsuites?[\s>/]", re.DOTALL)
_HOSTNAME = re.compile(rb"""\bhostname=(?:"([^"]+)"|'([^']+)')""")
_ABSOLUTE = (
    re.compile(rb"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'<>]*"),
    re.compile(rb"(?<!\\)\\\\[A-Za-z0-9._$-]+\\[^\s\"'<>]*"),
    re.compile(rb"(?<![\w.~-])/(?:home|Users|root|tmp|private|var|mnt|opt|srv|"
               rb"Volumes|runner|github|workspace|builds|usr)/[^\s\"'<>]*"),
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


def read_blobs(root: Path, blobs: list[str]) -> dict[str, bytes]:
    """The bytes of each blob, read in one `git cat-file --batch` call."""
    if not blobs:
        return {}
    proc = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                          input="\n".join(blobs).encode("ascii") + b"\n",
                          capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git cat-file failed in {root}: {detail}")
    out, pos, data = proc.stdout, 0, {}
    for _ in blobs:
        end = out.index(b"\n", pos)
        header = out[pos:end].split()
        if len(header) != 3:
            raise RuntimeError(f"git cat-file could not read {header!r}")
        size = int(header[2])
        data[header[0].decode("ascii")] = out[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
    return data


def is_junit_report(path: str, data: bytes) -> bool:
    """True for an oracle report by name, or any XML whose root is a JUnit suite."""
    name = path.rsplit("/", 1)[-1]
    if not name.endswith(".xml"):
        return False
    return name.startswith(_REPORT_PREFIX) or bool(_JUNIT_ROOT.match(data))


def findings(data: bytes) -> list[str]:
    """Each hostname a report names, then the absolute paths it holds."""
    out = []
    for match in _HOSTNAME.finditer(data):
        host = (match.group(1) or match.group(2)).decode("utf-8", "replace")
        if f"hostname {host}" not in out:
            out.append(f"hostname {host}")
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
    xml = [(p, b) for p, b in rows if p.endswith(".xml")]
    data = read_blobs(root, sorted({b for _, b in xml}))
    return [(p, data[b]) for p, b in xml if is_junit_report(p, data[b])]


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

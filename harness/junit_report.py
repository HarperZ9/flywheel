"""junit_report.py: a fresh JUnit report file for every pytest oracle run.

The pytest oracle grades a candidate by reading test outcomes back out of a
JUnit XML report. Until 2026-09-23 every run wrote that report to the same
`_oracle_junit.xml` in the task workdir, and nothing removed the previous one.
A candidate that ends the pytest process with exit code 0 before the report
plugin writes, for example `os._exit(0)` at import, left the last run's report
in place, and the oracle graded the candidate on it. A candidate with no
function at all read PASS after a reference solution ran in the same workdir,
on Windows and on Linux alike.

What this module does about it:

- Each run writes its report under a per-run name,
  `_oracle_junit_<nonce>.xml`, which does not exist before the run starts. The
  oracle removes the file after it reads it. So no run can read a report that
  another run wrote.
- The recorded command keeps the canonical `--junitxml=_oracle_junit.xml`
  token. The harness swaps that one token for the per-run name when it
  executes the command. A receipt stays byte-stable across runs, and a third
  party who types the recorded command gets the same test outcomes.
- The oracle reads a zero exit with no fresh report as a FAIL that the
  candidate caused. pytest writes the report on every normal exit, so an
  absent report means the process ended early.

Does not prove: candidate code runs inside the pytest process. It can read
the per-run name from sys.argv and write a forged report itself. The nonce
stops a stale report from grading a new run. It is not containment, and
python_execution_containment.py names the boundary that would be.
"""
from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path

JUNIT_NAME = "_oracle_junit.xml"
JUNIT_TOKEN = f"--junitxml={JUNIT_NAME}"
_PREFIX = "_oracle_junit"
_TOKEN_RE = re.compile(r"(?<!\S)" + re.escape(JUNIT_TOKEN) + r"(?!\S)")


def is_report_name(name: str) -> bool:
    """True for the canonical report name and for every per-run name.

    Receipt capture, receipt restore, and the cache key all skip these. A
    report is the oracle's output, and a receipt that carried one would carry
    the answer key into the directory where the re-run is graded.
    """
    return name.startswith(_PREFIX) and name.endswith(".xml")


def bind_report(cmd: str, workdir: str | Path) -> tuple[str, Path | None]:
    """The command to execute and the fresh report path it writes to.

    Swaps each canonical `--junitxml=_oracle_junit.xml` token for a per-run
    name, relative to the workdir so the command holds no absolute path. A
    command without the canonical token runs unchanged and returns no report
    path, so the caller reads no outcomes rather than a leftover file.
    """
    if not _TOKEN_RE.search(cmd):
        return cmd, None
    name = f"{_PREFIX}_{secrets.token_hex(8)}.xml"
    report = Path(workdir) / name
    report.unlink(missing_ok=True)
    return _TOKEN_RE.sub(f"--junitxml={name}", cmd), report


def discard_report(report: Path | None) -> None:
    """Remove a per-run report after the oracle has read it.

    A file that cannot be removed stays behind under its per-run name, where
    no later run reads it. That is clutter, not a wrong verdict, so the error
    is reported on stderr and the verdict stands.
    """
    if report is None:
        return
    try:
        report.unlink(missing_ok=True)
    except OSError as exc:
        print(f"junit_report: could not remove {report.name}: {exc}",
              file=sys.stderr)

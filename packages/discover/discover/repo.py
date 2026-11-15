"""Repository checks: README opening, GitHub About, package metadata,
CITATION.cff and the release notes for the version being released."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import cff, net, text
from .manifests import check_manifests
from .report import ERROR, WARN, Report

OPENING_LINES = 30
COMMAND_WINDOW = 60
MIN_TOPICS = 5
TAG = re.compile(r"^v?\d+\.\d+")


def load_config(root: Path) -> dict:
    path = root / "discover.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def check_readme(root: Path, report: Report) -> None:
    path = next((root / n for n in ("README.md", "README.rst", "README") if (root / n).is_file()), None)
    report.add("readme.present", "README", path is not None, ERROR, "", "add a README.md")
    if path is None:
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    para = text.first_paragraph(lines)
    ok = para is not None and para[0] <= OPENING_LINES and len(para[1]) >= 40
    where = f"line {para[0]}: {para[1][:90]}" if para else "no prose paragraph found"
    report.add("readme.benefit_first", path.name, ok, ERROR, where,
               f"open with one plain sentence, within the first {OPENING_LINES} lines, "
               "that says what the tool does for the reader")
    if para and len(para[1]) > 400:
        report.add("readme.opening_length", path.name, False, WARN,
                   f"{len(para[1])} characters", "keep the opening paragraph under 400 characters")
    cmd = text.first_command(lines, COMMAND_WINDOW)
    report.add("readme.run_command", path.name, cmd is not None, ERROR,
               f"line {cmd[0]}: {cmd[1][:80]}" if cmd else f"no command block in the first {COMMAND_WINDOW} lines",
               "put an install-and-run command in a fenced block near the top")


def check_github(root: Path, report: Report, offline: bool, slug: str | None) -> None:
    if offline:
        report.add("github.metadata", "GitHub", False, WARN, "skipped (--offline)",
                   "run without --offline to check the description and topics")
        return
    slug = slug or net.repo_slug(str(root))
    data = net.github_repo(slug) if slug else None
    if data is None:
        report.add("github.metadata", slug or "GitHub", False, WARN,
                   "could not read repository metadata", "set GITHUB_TOKEN or pass --github OWNER/REPO")
        return
    desc = (data.get("description") or "").strip()
    report.add("github.description", slug, 40 <= len(desc) <= 350, ERROR,
               f"{len(desc)} characters", "gh repo edit --description '<what it does, for whom>'")
    topics = data.get("topics") or []
    report.add("github.topics", slug, len(topics) >= MIN_TOPICS, ERROR,
               f"{len(topics)} topic(s)", f"gh repo edit --add-topic <topic> (need {MIN_TOPICS}+)")
    report.add("github.homepage", slug, bool(data.get("homepage")), WARN, "",
               "gh repo edit --homepage <docs or landing page URL>")


def check_citation(root: Path, report: Report, version: str | None) -> None:
    path = root / "CITATION.cff"
    if not path.is_file():
        report.add("citation.valid", "CITATION.cff", False, ERROR, "missing",
                   "add CITATION.cff (cff-version 1.2.0, message, title, authors, version)")
        return
    try:
        issues = cff.problems(cff.parse(path.read_text(encoding="utf-8")), version)
    except ValueError as exc:
        issues = [str(exc)]
    report.add("citation.valid", "CITATION.cff", not issues, ERROR, "; ".join(issues),
               "fix CITATION.cff; https://citation-file-format.github.io/")


def release_version(explicit: str | None) -> str | None:
    if explicit:
        return explicit.lstrip("v")
    ref = os.environ.get("GITHUB_REF_NAME", "")
    return ref.lstrip("v") if os.environ.get("GITHUB_REF_TYPE") == "tag" and TAG.match(ref) else None


def check_release_notes(root: Path, report: Report, notes: str | None, version: str | None) -> None:
    if notes:
        body, subject = Path(notes).read_text(encoding="utf-8"), notes
    else:
        log = root / "CHANGELOG.md"
        if not log.is_file():
            report.add("release.summary", "CHANGELOG.md", False, ERROR, "missing",
                       "add CHANGELOG.md or pass --notes FILE")
            return
        found = text.changelog_section(log.read_text(encoding="utf-8"), version)
        if found is None:
            report.add("release.summary", "CHANGELOG.md", False, ERROR,
                       f"no section for {version}", f"add a '## {version}' section")
            return
        subject, body = f"CHANGELOG.md {found[0]}", found[1]
    paras = text.paragraphs(body)
    first = paras[0] if paras else ""
    report.add("release.summary", subject, text.is_summary(first), ERROR,
               f"opens with: {first[:90]!r}",
               "open the section with one or two sentences on what the release does for the user, "
               "before any list")


def check_repo(root: Path, offline: bool = False, slug: str | None = None,
               notes: str | None = None, version: str | None = None) -> Report:
    report = Report("repo", str(root))
    config = load_config(root)
    check_readme(root, report)
    check_github(root, report, offline, slug or config.get("github"))
    pkg_version = check_manifests(root, config.get("manifests", []), report)
    released = release_version(version)
    check_citation(root, report, released or pkg_version)
    check_release_notes(root, report, notes, released)
    return report

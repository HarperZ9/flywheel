"""Package metadata checks for pyproject.toml, package.json and Cargo.toml.

Registry search reads these fields. PyPI search weighs the name, summary,
description and keywords; npm search matches name, description, README and
keywords. Classifiers drive PyPI's browse filters.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .report import ERROR, WARN, Report

MIN_KEYWORDS = 3


def _keywords(report: Report, subject: str, words: list, fix: str) -> None:
    words = [w for w in words or [] if isinstance(w, str) and w.strip()]
    report.add("package.keywords", subject, len(words) >= MIN_KEYWORDS, ERROR,
               f"{len(words)} keyword(s), need {MIN_KEYWORDS} or more", fix)


def check_pyproject(path: Path, report: Report) -> str | None:
    project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    subject = path.name
    _keywords(report, subject, project.get("keywords"),
              "add [project].keywords with the words a person would search for")
    classifiers = project.get("classifiers") or []
    has_lang = any(c.startswith("Programming Language :: Python") for c in classifiers)
    report.add("package.classifiers", subject, len(classifiers) >= 3 and has_lang, ERROR,
               f"{len(classifiers)} classifier(s); Python language classifier "
               f"{'present' if has_lang else 'missing'}",
               "add [project].classifiers: Development Status, Intended Audience, Topic, "
               "Programming Language :: Python :: 3")
    report.add("package.description", subject, bool(project.get("description")), ERROR,
               "", "set [project].description to one plain sentence about what it does")
    urls = {k.lower() for k in (project.get("urls") or {})}
    report.add("package.urls", subject,
               bool(urls & {"homepage", "documentation"}) and bool(urls & {"repository", "source"}),
               WARN, f"urls: {sorted(urls) or 'none'}",
               "add [project.urls] Homepage (or Documentation) and Repository (or Source)")
    version = project.get("version")
    return str(version) if version else None


def check_package_json(path: Path, report: Report) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    subject = path.name
    _keywords(report, subject, data.get("keywords"),
              "add a keywords array with the words a person would search for")
    report.add("package.description", subject, bool(data.get("description")), ERROR,
               "", "set description to one plain sentence about what it does")
    report.add("package.repository", subject, bool(data.get("repository")), ERROR,
               "", 'set repository to {"type": "git", "url": "git+https://github.com/OWNER/REPO.git"}')
    report.add("package.urls", subject, bool(data.get("homepage")) and bool(data.get("bugs")), WARN,
               "", "set homepage and bugs")
    report.add("package.license", subject, bool(data.get("license")), WARN, "", "set license")
    return data.get("version")


def check_cargo(path: Path, report: Report) -> str | None:
    package = tomllib.loads(path.read_text(encoding="utf-8")).get("package", {})
    subject = path.as_posix()
    words = package.get("keywords") or []
    report.add("package.keywords", subject, 1 <= len(words) <= 5, ERROR,
               f"{len(words)} keyword(s); crates.io takes 1 to 5",
               "add [package].keywords (up to five)")
    report.add("package.classifiers", subject, bool(package.get("categories")), ERROR,
               "no categories", "add [package].categories from crates.io/category_slugs")
    report.add("package.description", subject, bool(package.get("description")), ERROR,
               "", "set [package].description")
    report.add("package.repository", subject, bool(package.get("repository")), WARN,
               "", "set [package].repository")
    version = package.get("version")
    return version if isinstance(version, str) else None


CHECKERS = {"pyproject.toml": check_pyproject, "package.json": check_package_json,
            "Cargo.toml": check_cargo}


def check_manifests(root: Path, extra: list[str], report: Report) -> str | None:
    """Check every manifest at the root and each extra path; return the first version."""
    paths = [root / name for name in CHECKERS if (root / name).is_file()]
    paths += [root / p for p in extra if (root / p).is_file() and root / p not in paths]
    if not paths:
        report.add("package.manifest", root.name or str(root), False, WARN,
                   "no pyproject.toml, package.json or Cargo.toml found",
                   'list package manifests under "manifests" in discover.json')
        return None
    version = None
    for path in paths:
        checker = CHECKERS.get(path.name)
        if checker is None:
            continue
        try:
            found = checker(path, report)
        except (ValueError, tomllib.TOMLDecodeError) as exc:
            report.add("package.manifest", path.as_posix(), False, ERROR, f"cannot parse: {exc}")
            continue
        version = version or found
    return version

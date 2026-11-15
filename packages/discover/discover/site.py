"""Static site checks: page heads, JSON-LD, sitemap, robots and llms files.

Configuration lives in discover.json at the site root:

    {"origin": "https://example.github.io",
     "scope": "sitemap" | "all",
     "exclude": ["drafts/**"],
     "tools": [{"name": "Tool", "page": "tool.html", "version": "1.2.0",
                "registry": "pypi", "package": "tool-dist-name"}]}
"""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from urllib.parse import urlsplit

from . import head, site_files
from .report import ERROR, WARN, Report

ARTICLE_TYPES = {"Article", "ScholarlyArticle", "BlogPosting", "NewsArticle", "TechArticle"}
SOFTWARE_TYPES = {"SoftwareApplication", "SoftwareSourceCode", "WebApplication", "MobileApplication"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__"}


def load_config(root: Path) -> dict:
    path = root / "discover.json"
    if not path.is_file():
        raise SystemExit(f"discover: {path} is missing; a site check needs at least an origin")
    return json.loads(path.read_text(encoding="utf-8"))


def local_path(root: Path, origin: str, url: str) -> Path | None:
    """The file a URL on this origin serves, or None for another host."""
    if not url.startswith(origin):
        return None
    path = urlsplit(url).path.lstrip("/")
    target = root / path
    return target / "index.html" if path == "" or path.endswith("/") else target


def candidate_pages(root: Path, config: dict) -> list[Path]:
    out = []
    for path in root.rglob("*.html"):
        rel = path.relative_to(root).as_posix()
        if set(path.relative_to(root).parts) & SKIP_DIRS or rel.split("/")[0].startswith("."):
            continue
        if any(fnmatch.fnmatch(rel, pat) for pat in config.get("exclude", [])):
            continue
        out.append(path)
    return sorted(out)


def check_head(page: head.Page, rel: str, root: Path, origin: str, report: Report,
               sev: str = ERROR) -> None:
    title = page.title
    report.add("page.title", rel, bool(title), sev, "", "add a <title> that names the page's subject")
    if title:
        report.add("page.title_length", rel, 15 <= len(title) <= 70, WARN, f"{len(title)} characters",
                   "keep titles between 15 and 70 characters, key phrase first")
    desc = page.meta.get("description", "")
    report.add("page.description", rel, bool(desc), sev, "",
               "add <meta name=\"description\"> answering the question a searcher would ask")
    if desc:
        report.add("page.description_length", rel, 70 <= len(desc) <= 160, WARN,
                   f"{len(desc)} characters", "keep descriptions between 70 and 160 characters")
    canon = page.canonical
    report.add("page.canonical", rel, canon.startswith(origin), sev, canon or "missing",
               f"add <link rel=\"canonical\" href=\"{origin}/...\">")
    missing = [k for k in ("og:title", "og:description", "og:image", "twitter:card") if not page.meta.get(k)]
    report.add("page.social_card", rel, not missing, sev, "missing " + ", ".join(missing),
               "add Open Graph title, description and image, and twitter:card")
    image = page.meta.get("og:image", "")
    if image:
        target = local_path(root, origin, image)
        report.add("page.social_image", rel, target is None or target.is_file(), sev,
                   image, "point og:image at an image that exists in the site")


def check_ld(page: head.Page, rel: str, tools: dict[str, dict], report: Report,
             sev: str = ERROR) -> None:
    types, errors, nodes = page.ld_types()
    report.add("page.jsonld_valid", rel, not errors, sev, "; ".join(errors)[:200],
               "fix the JSON in the application/ld+json block")
    needs = []
    if page.meta.get("og:type") == "article":
        needs.append(("Article", ARTICLE_TYPES))
    if rel in tools:
        needs.append(("SoftwareApplication or SoftwareSourceCode", SOFTWARE_TYPES))
    if page.has_video:
        needs.append(("VideoObject", {"VideoObject"}))
    for label, accepted in needs:
        report.add("page.jsonld_type", rel, bool(types & accepted), sev, f"needs {label}",
                   f"add a schema.org {label} node to the page's JSON-LD")
    tool = tools.get(rel)
    if tool and tool.get("version"):
        apps = [n for n in nodes if n.get("@type") == "SoftwareApplication"]
        found = {str(n.get("softwareVersion", "")) for n in apps}
        report.add("page.jsonld_version", rel, tool["version"] in found, sev,
                   f"softwareVersion {sorted(found) or 'absent'}, expected {tool['version']}",
                   "set SoftwareApplication.softwareVersion to the released version")


def check_site(root: Path, online: bool = False) -> Report:
    config = load_config(root)
    origin = config["origin"].rstrip("/")
    report = Report("site", origin)
    listed = site_files.check_sitemap(root, origin, report)
    site_files.check_robots(root, origin, report)
    tools = {t["page"]: t for t in config.get("tools", []) if t.get("page")}
    site_files.check_llms(root, config.get("tools", []), report, online)
    # With scope "sitemap", pages the sitemap lists must pass; other indexable
    # pages are still checked, at warning level.
    strict_all = config.get("scope", "all") == "all"
    for path in candidate_pages(root, config):
        rel = path.relative_to(root).as_posix()
        page = head.read(path.read_text(encoding="utf-8", errors="replace"))
        if page.noindex or page.refresh:
            continue
        sev = ERROR if strict_all or path in listed or rel in tools else WARN
        check_head(page, rel, root, origin, report, sev)
        check_ld(page, rel, tools, report, sev)
        report.add("sitemap.coverage", rel, path in listed, WARN, "indexable page not in sitemap.xml",
                   "list the page in sitemap.xml, or mark it noindex")
    return report

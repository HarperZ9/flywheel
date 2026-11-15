"""Site-wide files: sitemap.xml, robots.txt, llms.txt and llms-full.txt."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from . import net
from .report import ERROR, WARN, Report

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# Crawlers that feed search results, including AI search. Blocking one removes
# the site from that product's answers and citations.
SEARCH_AGENTS = ("Googlebot", "Bingbot", "OAI-SearchBot", "PerplexityBot", "Claude-SearchBot")


def _local(root: Path, origin: str, url: str) -> Path | None:
    if not url.startswith(origin):
        return None
    path = urlsplit(url).path.lstrip("/")
    return root / path / "index.html" if path == "" or path.endswith("/") else root / path


def check_sitemap(root: Path, origin: str, report: Report) -> set[Path]:
    path = root / "sitemap.xml"
    if not path.is_file():
        report.add("sitemap.present", "sitemap.xml", False, ERROR, "missing", "publish sitemap.xml")
        return set()
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        report.add("sitemap.present", "sitemap.xml", False, ERROR, f"does not parse: {exc}")
        return set()
    report.add("sitemap.present", "sitemap.xml", True)
    listed: set[Path] = set()
    urls = tree.getroot().findall(f"{NS}url")
    dated = 0
    for node in urls:
        loc = (node.findtext(f"{NS}loc") or "").strip()
        dated += bool((node.findtext(f"{NS}lastmod") or "").strip())
        target = _local(root, origin, loc)
        ok = target is not None and target.is_file()
        report.add("sitemap.live", loc, ok, ERROR, "" if ok else "no file serves this URL",
                   "remove the entry or restore the page")
        if target is not None:
            listed.add(target)
    report.add("sitemap.lastmod", "sitemap.xml", bool(urls) and dated == len(urls), WARN,
               f"{dated} of {len(urls)} entries carry lastmod",
               "give every entry a lastmod that changes only when the page content changes")
    return listed


def _groups(text: str) -> list[tuple[list[str], list[str]]]:
    groups: list[tuple[list[str], list[str]]] = []
    agents: list[str] = []
    rules: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        if key.lower() == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif key.lower() == "disallow" and agents:
            rules.append(value)
        elif agents and key.lower() == "allow":
            rules.append("+" + value)
    if agents:
        groups.append((agents, rules))
    return groups


def blocked(text: str, agent: str) -> bool:
    """True when the group that applies to `agent` disallows the whole site."""
    groups = _groups(text)
    own = [rules for agents, rules in groups if agent.lower() in agents]
    rules = own[0] if own else next((r for a, r in groups if "*" in a), [])
    return "/" in rules and "+/" not in rules


def check_robots(root: Path, origin: str, report: Report) -> None:
    path = root / "robots.txt"
    if not path.is_file():
        report.add("robots.present", "robots.txt", False, ERROR, "missing", "publish robots.txt")
        return
    body = path.read_text(encoding="utf-8")
    report.add("robots.sitemap", "robots.txt", f"Sitemap: {origin}/sitemap.xml" in body, ERROR, "",
               f"add 'Sitemap: {origin}/sitemap.xml'")
    for agent in SEARCH_AGENTS:
        report.add("robots.search_agents", agent, not blocked(body, agent), ERROR,
                   "disallowed from the whole site", f"allow {agent}; it feeds search results")


def _section(body: str, name: str) -> str:
    match = re.search(r"(?mi)^#{2,3}\s+.*\b" + re.escape(name) + r"\b.*$", body)
    if not match:
        return ""
    rest = body[match.end():]
    nxt = re.search(r"(?m)^#{2,3}\s", rest)
    return rest[: nxt.start()] if nxt else rest


def check_llms(root: Path, tools: list[dict], report: Report, online: bool) -> None:
    short, full = root / "llms.txt", root / "llms-full.txt"
    for path in (short, full):
        ok = path.is_file() and path.read_text(encoding="utf-8").startswith("# ")
        report.add("llms.present", path.name, ok, ERROR, "" if ok else "missing or no '# ' title",
                   f"publish {path.name} with a '# Name' first line (llmstxt.org)")
    if not (short.is_file() and full.is_file()):
        return
    short_body, full_body = short.read_text(encoding="utf-8"), full.read_text(encoding="utf-8")
    for tool in tools:
        name = tool["name"]
        report.add("llms.lists_tool", name, name.lower() in short_body.lower(), ERROR, "not in llms.txt",
                   f"link {name} from llms.txt")
        section = _section(full_body, name)
        report.add("llms.full_tool", name, bool(section), ERROR, "no section in llms-full.txt",
                   f"add a '## {name}' section to llms-full.txt")
        version = tool.get("version")
        if section and version:
            report.add("llms.version", name, version in section, ERROR,
                       f"section does not mention {version}", f"update {name} to {version} in llms-full.txt")
        if online and version and tool.get("registry") and tool.get("package"):
            latest = net.latest_version(tool["registry"], tool["package"])
            ok = latest is not None and latest == version
            report.add("release.latest", name, ok, ERROR if latest else WARN,
                       f"discover.json says {version}, {tool['registry']} says {latest or 'unknown'}",
                       "update the version in discover.json, llms-full.txt and the JSON-LD")

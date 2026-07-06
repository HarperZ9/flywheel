"""feeds.py — normalize scraped/curated sources into a scout catalog.

The friction this converts into capability: ingesting research signal (Reddit,
X, YouTube, articles) is manual browser work today. This module makes the LAST
mile reusable — given a raw scrape (however it was captured), produce the
canonical scout-catalog shape (id/title/text/ref/theme) with dedup, provenance,
and Telos-domain tagging, so `intake.digest` / `wiki.build` / `flywheel.spin`
consume it directly.

It does NOT scrape (that needs a live browser / MCP); it is the deterministic
normalization + domain-mapping layer beneath the scraper, and the place the
operator's ~60-subreddit domain map lives as a durable artifact. `coverage()`
reports sampled-vs-remaining so breadth is never silently capped.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

# The operator's research surface -> Telos domains. Durable artifact: this is
# where "which fields does Project Telos touch" is recorded and extended.
DOMAIN_MAP = {
    "machinelearningnews": "ml-research", "artificial": "ml-research",
    "ArtificialInteligence": "ml-research", "accelerate": "ml-research",
    "MachineLearningJobs": "ml-research",
    "OpenSourceAI": "local-inference", "huggingface": "local-inference",
    "opensource": "opensource", "coolgithubprojects": "opensource",
    "ControlProblem": "ai-safety", "rationalphilosophy": "ai-safety",
    "ClaudeAIJailbreak": "ai-safety",
    "OntologyEngineering": "knowledge-systems", "AestheticWiki": "knowledge-systems",
    "etymology": "knowledge-systems", "neography": "knowledge-systems",
    "Geometry": "knowledge-systems", "GeometryIsNeat": "knowledge-systems",
    "GrassrootsResearch": "knowledge-systems",
    "netsec": "security", "cybersecurity": "security", "devsecops": "security",
    "oscp": "security",
    "GraphicsProgramming": "graphics-render", "retrocgi": "graphics-render",
    "vintagecgi": "graphics-render", "vfx": "graphics-render", "colorists": "graphics-render",
    "generative": "generative-art", "proceduralgeneration": "generative-art",
    "fractals": "generative-art", "glitch_art": "generative-art",
    "DitherArt": "generative-art", "pixelsorting": "generative-art",
    "PlotterArt": "generative-art", "PlotterCode": "generative-art",
    "artandcode": "generative-art", "cellular_automata": "generative-art",
    "blotterart": "generative-art",
    "sounddesign": "audio", "modular": "audio",
    "complexsystems": "complexity", "ScaleSpace": "complexity",
    "ProgrammingLanguages": "languages-compilers", "rust": "systems",
    "programming": "systems",
    "gamedev": "gamedev", "IndieDev": "gamedev",
    "SideProject": "product", "ProductManagement": "product",
    "design_critiques": "design", "graphic_design": "design", "design": "design",
    "advertising": "marketing", "DigitalMarketing": "marketing",
    "fintech": "finance", "investing": "finance",
    "FifthWorldPics": "aesthetic", "ASCII": "aesthetic",
}


def domain_of(sub: str) -> str:
    return DOMAIN_MAP.get(sub, "unmapped")


def _rid(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:8]
    return f"reddit/{parts[0]}/{h}"


def _row(id_: str, title: str, text: str, ref: str, theme: str, source: str) -> dict:
    return {"id": id_, "title": title[:160], "text": text,
            "ref": ref, "theme": theme, "source": source}


def normalize_scrape(scrape: dict) -> list[dict]:
    """Turn a raw scrape (subs / threads / video / articles) into catalog rows.
    Deterministic and dedup'd (by normalized text). Provenance in `ref`/`source`."""
    rows: list[dict] = []
    seen: set[str] = set()

    def add(row: dict) -> None:
        key = " ".join(row["text"].lower().split())[:120]
        if key and key not in seen:
            seen.add(key)
            rows.append(row)

    captured = str(scrape.get("captured", ""))

    for sub, titles in (scrape.get("subs") or {}).items():
        theme = domain_of(sub)
        for t in titles:
            t = str(t).strip()
            if not t:
                continue
            add(_row(_rid(sub, t), t, t, f"reddit:r/{sub}", theme, f"reddit/{captured}"))

    for th in (scrape.get("threads") or []):
        add(_row(str(th.get("id", "")), str(th.get("title", "")),
                 str(th.get("text", th.get("title", ""))),
                 f"reddit:r/{th.get('sub','')}", str(th.get("theme", "")), f"reddit-thread/{captured}"))

    v = scrape.get("video")
    if v:
        add(_row(str(v.get("id", "")), str(v.get("title", "")),
                 str(v.get("text", "")), "youtube", str(v.get("theme", "")), f"youtube/{captured}"))

    for a in (scrape.get("articles") or []):
        add(_row(str(a.get("id", "")), str(a.get("title", "")),
                 str(a.get("text", "")), "article", str(a.get("theme", "")), f"article/{captured}"))

    return rows


def merge(*catalogs: list[dict]) -> list[dict]:
    """Union of catalogs, dedup'd by normalized text, ids kept unique."""
    out: list[dict] = []
    seen_text: set[str] = set()
    seen_ids: set[str] = set()
    for cat in catalogs:
        for row in cat:
            key = " ".join(str(row.get("text", "")).lower().split())[:120]
            rid = str(row.get("id", ""))
            if key in seen_text:
                continue
            if rid in seen_ids:
                rid = rid + "-" + hashlib.sha256(key.encode()).hexdigest()[:4]
                row = {**row, "id": rid}
            seen_text.add(key)
            seen_ids.add(rid)
            out.append(row)
    return out


@dataclass
class Coverage:
    sampled: list[str]
    remaining: list[str]
    total: int

    def report(self) -> str:
        pct = round(100 * len(self.sampled) / max(self.total, 1))
        return (f"coverage: {len(self.sampled)}/{self.total} subs sampled ({pct}%), "
                f"{len(self.remaining)} remaining -> feed to the scraper next.")


def coverage(scrape: dict) -> Coverage:
    """Honest breadth accounting — never silently cap. What was sampled vs the
    full operator list, so the next crawl targets the remainder."""
    sampled = list(scrape.get("sampled_subs", []) or list((scrape.get("subs") or {}).keys()))
    remaining = list(scrape.get("not_yet_swept", []))
    return Coverage(sampled=sampled, remaining=remaining,
                    total=len(sampled) + len(remaining))

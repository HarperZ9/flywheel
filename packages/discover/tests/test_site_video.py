"""Site and video checks against fixtures built in a temp dir."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discover import site_files
from discover.site import check_site
from discover.video import check_manifest

ORIGIN = "https://example.org"
GOOD_PAGE = """<!doctype html><html><head><title>Tool: checks files for drift</title>
<meta name="description" content="Tool checks files for drift and names each file that changed since you recorded it.">
<link rel="canonical" href="https://example.org/tool.html">
<meta property="og:title" content="Tool"><meta property="og:description" content="Checks drift.">
<meta property="og:image" content="https://example.org/card.png"><meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
{"@type":"SoftwareApplication","name":"Tool","softwareVersion":"1.2.0"}]}</script>
</head><body><video controls poster="p.jpg"><source src="v.mp4"></video></body></html>"""


def site(files: dict[str, str], config: dict) -> Path:
    root = Path(tempfile.mkdtemp())
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    (root / "discover.json").write_text(json.dumps(config), encoding="utf-8")
    return root


BASE = {
    "tool.html": GOOD_PAGE, "card.png": "x",
    "sitemap.xml": '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                   "<url><loc>https://example.org/tool.html</loc><lastmod>2026-10-23</lastmod></url></urlset>",
    "robots.txt": "User-agent: *\nAllow: /\nSitemap: https://example.org/sitemap.xml\n",
    "llms.txt": "# Example\n\n- [Tool](https://example.org/tool.html)\n",
    "llms-full.txt": "# Example\n\n## Tool\n\nVersion 1.2.0. Checks drift.\n",
}
CONFIG = {"origin": ORIGIN, "scope": "sitemap",
          "tools": [{"name": "Tool", "page": "tool.html", "version": "1.2.0"}]}


class SiteChecks(unittest.TestCase):
    def test_page_needs_video_markup(self) -> None:
        report = check_site(site(BASE, CONFIG))
        blocking = {(f.check, f.message) for f in report.blocking}
        self.assertEqual(blocking, {("page.jsonld_type", "needs VideoObject")})

    def test_stale_version_and_missing_card_block(self) -> None:
        files = dict(BASE, **{"tool.html": GOOD_PAGE.replace('"1.2.0"', '"1.1.0"').replace(
            '<meta name="twitter:card" content="summary_large_image">', "")})
        checks = {f.check for f in check_site(site(files, CONFIG)).blocking}
        self.assertTrue({"page.jsonld_version", "page.social_card"} <= checks)

    def test_llms_must_carry_the_version(self) -> None:
        files = dict(BASE, **{"llms-full.txt": "# Example\n\n## Tool\n\nChecks drift.\n"})
        checks = {f.check for f in check_site(site(files, CONFIG)).blocking}
        self.assertIn("llms.version", checks)

    def test_robots_blocking_an_ai_search_crawler(self) -> None:
        body = "User-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        self.assertTrue(site_files.blocked(body, "OAI-SearchBot"))
        self.assertFalse(site_files.blocked(body, "Googlebot"))


VIDEO = {
    "id": "v1", "title": "Viral voting machine clip: what the record shows",
    "key_phrase": "voting machine clip",
    "description": ("A viral clip says a machine flipped votes. We check the county record.\n\n"
                    "0:00 The claim\n0:30 The record\n1:10 The verdict\n\n"
                    "Sources:\nhttps://example.org/record\n\n#elections #factcheck #voting"),
    "sources": ["https://example.org/record"],
    "pinned_comment": "What if the clip had been filmed a day later?",
    "shorts_cut": "The 20-second record reveal.",
}


class VideoChecks(unittest.TestCase):
    def run_one(self, video: dict) -> set[str]:
        path = Path(tempfile.mkdtemp()) / "m.json"
        path.write_text(json.dumps({"videos": [video]}), encoding="utf-8")
        return {f.check for f in check_manifest(path).failures}

    def test_good_video_passes(self) -> None:
        self.assertEqual(self.run_one(VIDEO), set())

    def test_bad_video(self) -> None:
        bad = dict(VIDEO, title="x" * 80, pinned_comment="Comment YES below if you agree!",
                   description="#tag https://x.org\n0:05 start\n")
        found = self.run_one(bad)
        for check in ("video.title_length", "video.chapters", "video.description_lead",
                      "video.pinned_question", "video.no_bait", "video.hashtags"):
            self.assertIn(check, found, check)


if __name__ == "__main__":
    unittest.main()

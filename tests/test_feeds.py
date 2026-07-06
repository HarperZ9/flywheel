"""feeds falsifier — normalization is deterministic, dedup'd, provenance-kept.

Load-bearing properties:
  1. normalize_scrape produces rows the scout can consume (intake.validate passes).
  2. duplicate titles collapse (the scraper's doubled DOM hits don't inflate).
  3. domain tagging is correct for known subs and honest ("unmapped") for unknown.
  4. provenance (ref + source) survives normalization — every row is traceable.
  5. coverage() reports remaining subs (breadth is never silently capped).
"""
from harness import feeds
from harness.intake import validate_catalog

SCRAPE = {
    "captured": "2026-07-06",
    "sampled_subs": ["machinelearningnews", "OntologyEngineering"],
    "not_yet_swept": ["netsec", "rust", "fractals"],
    "subs": {
        "machinelearningnews": [
            "Leanstral 1.5 solving 587 of 672 PutnamBench problems",
            "Leanstral 1.5 solving 587 of 672 PutnamBench problems",  # dup (DOM doubling)
            "NVIDIA HORIZON evolves git worktrees, 100% RTL benchmark",
        ],
        "OntologyEngineering": ["Context as the Only Primitive; Proto-Formalism"],
        "someRandomSub": ["a post about nothing in particular"],
    },
    "video": {"id": "yt-x", "title": "V", "text": "global workspace broadcast", "theme": "interp"},
}


def test_rows_are_scout_consumable():
    rows = feeds.normalize_scrape(SCRAPE)
    assert rows
    assert validate_catalog(rows) == []  # intake curator gate passes


def test_duplicate_titles_collapse():
    rows = feeds.normalize_scrape(SCRAPE)
    putnam = [r for r in rows if "PutnamBench" in r["text"]]
    assert len(putnam) == 1, "doubled DOM titles must dedup to one row"


def test_domain_tagging_known_and_unknown():
    assert feeds.domain_of("machinelearningnews") == "ml-research"
    assert feeds.domain_of("OntologyEngineering") == "knowledge-systems"
    assert feeds.domain_of("someRandomSub") == "unmapped"
    rows = feeds.normalize_scrape(SCRAPE)
    onto = [r for r in rows if r["ref"] == "reddit:r/OntologyEngineering"][0]
    assert onto["theme"] == "knowledge-systems"


def test_provenance_survives():
    rows = feeds.normalize_scrape(SCRAPE)
    for r in rows:
        assert r["ref"] and r["source"], "every row must be traceable to its source"
    vid = [r for r in rows if r["id"] == "yt-x"][0]
    assert vid["ref"] == "youtube"


def test_merge_dedups_across_catalogs():
    a = feeds.normalize_scrape(SCRAPE)
    b = feeds.normalize_scrape(SCRAPE)
    merged = feeds.merge(a, b)
    assert len(merged) == len(a), "merging a catalog with itself adds nothing"


def test_coverage_reports_remaining():
    cov = feeds.coverage(SCRAPE)
    assert cov.total == 5 and len(cov.remaining) == 3
    assert "remaining" in cov.report()

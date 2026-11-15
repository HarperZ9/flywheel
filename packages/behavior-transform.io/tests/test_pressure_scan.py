import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest
import pressure_scan


def test_score_formula_tier1_single_line():
    """one tier1 hit in 1-line doc: raw=10.0, lines=1 => min(100, round(10/1*1000,1))=100.0"""
    hits = [{"severity": "tier1"}]
    assert pressure_scan._pressure_score(hits, total_lines=1) == 100.0


def test_score_formula_tier2_low_density():
    """one tier2 hit in 1000-line doc: raw=2.0, lines=1000 => round(2/1000*1000,1)=2.0"""
    hits = [{"severity": "tier2"}]
    assert pressure_scan._pressure_score(hits, total_lines=1000) == 2.0


def test_score_zero_no_hits():
    """no hits returns 0.0"""
    assert pressure_scan._pressure_score([], total_lines=100) == 0.0


def test_score_clamps_at_100():
    """multiple tier1 hits clamp score at 100.0"""
    hits = [{"severity": "tier1"}] * 100
    assert pressure_scan._pressure_score(hits, total_lines=1) == 100.0


def test_score_mixed_weights():
    """tier1 (10.0) and tier2 (2.0) combined correctly"""
    hits = [{"severity": "tier1"}, {"severity": "tier2"}]
    # raw = 10.0 + 2.0 = 12.0, lines = 10 => round(12/10*1000, 1) = 1200.0 clamped to 100.0
    assert pressure_scan._pressure_score(hits, total_lines=10) == 100.0


def test_score_zero_lines_safety():
    """zero lines uses max(total_lines, 1) to avoid division by zero"""
    hits = [{"severity": "tier1"}]
    # raw = 10.0, lines = 0 => max(0, 1) = 1 => round(10/1*1000, 1) = 100.0
    assert pressure_scan._pressure_score(hits, total_lines=0) == 100.0


def test_tier2_suppressed_without_flag(tmp_path):
    """when include_tier2=False, tier2 hits are not returned"""
    from vocabulary_map import by_severity
    t2 = by_severity("tier2")
    if not t2:
        pytest.skip("no tier2 calibrations defined")
    term = t2[0].original
    f = tmp_path / "test.py"
    f.write_text(f"# {term}\n")
    hits = pressure_scan._scan_file(f, include_tier2=False)
    assert all(h["severity"] != "tier2" for h in hits)


def test_tier2_included_with_flag(tmp_path):
    # A non-alias tier2 term must register as a tier2-severity hit only when
    # include_tier2=True. _scan_file skips no-op aliases (calibrated == original),
    # so we pick a tier2 term that actually produces a hit.
    from vocabulary_map import by_severity
    real = [c for c in by_severity("tier2") if c.calibrated != c.original]
    if not real:
        pytest.skip("no non-alias tier2 calibrations defined")
    chosen = None
    for c in real:
        probe = tmp_path / "probe.py"
        probe.write_text(f"# {c.original}\n")
        if any(h["severity"] == "tier2"
               for h in pressure_scan._scan_file(probe, include_tier2=True)):
            chosen = c.original
            break
    assert chosen is not None, "expected at least one tier2 term to register a hit"
    f = tmp_path / "t.py"
    f.write_text(f"# {chosen}\n")
    assert any(h["severity"] == "tier2"
               for h in pressure_scan._scan_file(f, include_tier2=True))
    assert all(h["severity"] != "tier2"
               for h in pressure_scan._scan_file(f, include_tier2=False))


def test_scan_file_returns_list(tmp_path):
    """_scan_file returns a list"""
    f = tmp_path / "test.py"
    f.write_text("x = 1\n")
    result = pressure_scan._scan_file(f, include_tier2=True)
    assert isinstance(result, list)


def test_scan_file_hit_has_severity_key(tmp_path):
    """each hit dict has 'severity' key"""
    from vocabulary_map import by_severity
    t1 = by_severity("tier1")
    if not t1:
        pytest.skip("no tier1 calibrations defined")
    term = t1[0].original
    f = tmp_path / "test.py"
    f.write_text(f"# {term}\n")
    hits = pressure_scan._scan_file(f, include_tier2=True)
    # Filter for non-alias hits (calibrated != original)
    real_hits = [h for h in hits if h.get("calibrated") != h.get("original")]
    if real_hits:
        for h in real_hits:
            assert "severity" in h
            assert h["severity"] in ("tier1", "tier2")


def test_noqa_line_skipped(tmp_path):
    """lines with '# noqa: AUP-ALIAS' are skipped"""
    from vocabulary_map import by_severity
    t1 = by_severity("tier1")
    if not t1:
        pytest.skip("no tier1 calibrations defined")
    term = t1[0].original
    f = tmp_path / "test.py"
    # First line has the term with noqa, second has it without
    f.write_text(f"# {term}  # noqa: AUP-ALIAS\n# {term}\n")
    hits = pressure_scan._scan_file(f, include_tier2=True)
    # Filter for real (non-alias) hits
    real_hits = [h for h in hits if h.get("calibrated") != h.get("original")]
    # Should only find hits on line 2, not line 1
    if real_hits:
        assert all(h["line"] > 1 for h in real_hits), "noqa line should be skipped"


def test_walk_yields_files_in_directory(tmp_path):
    """_walk yields files from directory tree"""
    f1 = tmp_path / "test.py"
    f1.write_text("x = 1\n")
    f2 = tmp_path / "test.md"
    f2.write_text("# doc\n")
    paths = list(pressure_scan._walk([tmp_path]))
    assert f1 in paths or f2 in paths


def test_walk_skips_git_dir(tmp_path):
    """_walk skips .git and other SKIP_DIRS directories"""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    f_in_git = git_dir / "config"
    f_in_git.write_text("content")
    paths = list(pressure_scan._walk([tmp_path]))
    assert not any(".git" in str(p) for p in paths)


def test_walk_skips_pycache(tmp_path):
    """_walk skips __pycache__ directory"""
    cache_dir = tmp_path / "__pycache__"
    cache_dir.mkdir()
    f_in_cache = cache_dir / "test.pyc"
    f_in_cache.write_bytes(b"")
    paths = list(pressure_scan._walk([tmp_path]))
    assert not any("__pycache__" in str(p) for p in paths)


def test_walk_filters_by_extension(tmp_path):
    """_walk only yields files with SCAN_EXTENSIONS"""
    f_py = tmp_path / "test.py"
    f_py.write_text("x = 1\n")
    f_bin = tmp_path / "binary.so"
    f_bin.write_bytes(b"\x00")
    paths = list(pressure_scan._walk([tmp_path]))
    assert f_py in paths
    assert f_bin not in paths


def test_scan_extensions_contains_py():
    """SCAN_EXTENSIONS includes .py"""
    assert ".py" in pressure_scan.SCAN_EXTENSIONS


def test_scan_extensions_contains_pyi():
    """SCAN_EXTENSIONS includes .pyi"""
    assert ".pyi" in pressure_scan.SCAN_EXTENSIONS


def test_scan_extensions_contains_md():
    """SCAN_EXTENSIONS includes .md"""
    assert ".md" in pressure_scan.SCAN_EXTENSIONS


def test_tier_weight_tier1():
    """_TIER_WEIGHT has tier1 weight of 10.0"""
    assert pressure_scan._TIER_WEIGHT["tier1"] == 10.0


def test_tier_weight_tier2():
    """_TIER_WEIGHT has tier2 weight of 2.0"""
    assert pressure_scan._TIER_WEIGHT["tier2"] == 2.0

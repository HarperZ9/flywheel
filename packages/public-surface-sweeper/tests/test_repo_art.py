"""The README's diagrams are generated from a spec, so they go stale like any other
derived file: somebody adds a rule, nobody re-renders, and the picture describes a
sweeper that no longer exists. The gate re-renders and compares bytes; this runs it
under pytest, so a drifted drawing fails the suite instead of quietly shipping."""

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"
_SPEC = _REPO / "docs" / "art" / "public-surface-sweeper.art.json"

GATES = (
    "spec.present", "art.matches_spec", "art.render_is_deterministic",
    "art.identity_per_repository", "art.seed_is_recorded",
    "art.no_local_paths_or_em_dashes", "art.spec_words_reach_the_drawing",
    "art.note_survives_the_wrapper", "art.return_edge_stays_on_its_row",
    "art.every_illustration_is_shown", "art.tagline_stays_inside_its_rule",
    "art.outcome_fits_its_box", "art.card_draws_shapes_not_digits",
    "art.card_text_fits_its_column", "art.card_widths_bound_every_face",
    "art.card_draws_measured_characters", "art.card_carries_one_mark",
    "art.card_alt_reaches_the_readme", "art.the_gate_can_fail",
)

DRAWINGS = ("docs/art/public-surface-sweeper-header.svg", "docs/art/sweep-lane.svg",
            "docs/art/matrix-lane.svg", "docs/art/rule-severity.svg")


def _receipt() -> dict:
    out = subprocess.run([sys.executable, str(_GATE), "--json"],
                         cwd=_REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "public-surface-sweeper.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_card_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/public-surface-sweeper.art.json"]
    drawn = {out["file"]: out for out in receipt["outputs"]}
    assert set(drawn) == set(DRAWINGS)
    for path, out in drawn.items():
        assert len(out["sha256"]) == 64, path
        assert out["bytes"] > 0, path


def test_a_gate_that_cannot_fail_is_not_a_gate(tmp_path, monkeypatch):
    """Point the outcome-box check at a note too wide for its box and it has to
    complain. Without this, a green suite proves only that the gate ran."""
    sys.path.insert(0, str(_REPO / "tools"))
    import check_repo_art as gate
    spec = json.loads(_SPEC.read_text("utf-8"))
    spec["flows"][0]["outcomes"][0]["note"] = "x" * 80
    (tmp_path / "public-surface-sweeper.art.json").write_text(json.dumps(spec),
                                                              encoding="utf-8")
    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1


# sweep-lane.svg says what one sweep reads and in what order, matrix-lane.svg says how
# a workspace collapses to one verdict per repository, and rule-severity.svg says what
# ten of the rules refuse. Those are claims about the package, and nothing under tools/
# can settle them. Every count, every filter and every outcome below is driven against
# the code that ships.

from public_surface_sweeper import workspace as ws  # noqa: E402
from public_surface_sweeper.cli import main  # noqa: E402
from public_surface_sweeper.file_io import MAX_SCAN_BYTES, read_text_file  # noqa: E402
from public_surface_sweeper.readme_delivery import readme_delivery_findings  # noqa: E402
from public_surface_sweeper.summary import summarize_findings  # noqa: E402
from public_surface_sweeper.sweeper import (  # noqa: E402
    REQUIRED_FILES, SKIP_DIRS, scan, scan_delivery_surface,
)
from public_surface_sweeper.text_hygiene import (  # noqa: E402
    SECRET_PATTERNS, secret_rules, text_findings,
)

# Assembled here rather than written whole, so that no complete credential shape and
# no em dash character sits in a file the sweeper reads. Its own rules apply to it,
# and a fixture that trips them is a finding like any other.
EM = "\u2014"
SHAPES = {
    "private-key": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "github-token": "ghp_" + "A" * 24,
    "openai-key": "sk-" + "b" * 24,
    "aws-access-key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "slack-token": "xoxb-" + "1234567890-abcdef",
}
README = ("# Demo\n\n![a picture of the tool](docs/brand/hero.png)\n\n"
          "## Why it matters\n\nIt explains itself.\n\n"
          "## Try it\n\n```bash\npython -m demo\n```\n\n"
          "## Contributing\n\nOpen a pull request.\n")


def _card() -> dict:
    return json.loads(_SPEC.read_text("utf-8"))["cards"][0]


def _clean(root: Path, slug: str = "HarperZ9/demo") -> Path:
    """A repository the sweeper has nothing to say about."""
    (root / "docs" / "brand").mkdir(parents=True)
    (root / "docs" / "brand" / "hero.png").write_bytes(b"not really an image")
    (root / "README.md").write_text(README, encoding="utf-8")
    for name in ("LICENSE", "AUTHORS.md", "CONTRIBUTING.md", "CHANGELOG.md",
                 "AGENTS.md", "USAGE.md"):
        (root / name).write_text("placeholder\n", encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("on: push\n", encoding="utf-8")
    (root / ".github" / "FUNDING.yml").write_text("github: HarperZ9\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/' + slug + ".git\n",
        encoding="utf-8")
    return root


def _rules(findings) -> set:
    return {item.rule for item in findings}


def test_a_clean_repository_raises_nothing_at_all(tmp_path):
    """Everything below reads as a finding only against this baseline, so the
    baseline has to be genuinely quiet first."""
    assert scan(_clean(tmp_path)) == []


def test_the_walk_never_enters_twenty_five_directory_names(tmp_path):
    """The drawn count, and the consequence: a file inside a skipped directory
    is not read, so nothing in it can be raised."""
    assert len(SKIP_DIRS) == 25
    root = _clean(tmp_path)
    for name in (".venv", "node_modules", "__pycache__"):
        (root / name).mkdir()
        (root / name / "notes.md").write_text("an " + EM + " em dash\n", encoding="utf-8")
    assert scan(root) == []


def test_only_decodable_text_under_a_megabyte_is_read(tmp_path):
    """Three ways a file is passed over, none of which produce a finding."""
    assert MAX_SCAN_BYTES == 1_000_000
    big, binary, latin = (tmp_path / n for n in ("big.md", "bin.md", "latin.md"))
    big.write_bytes(b"a" * (MAX_SCAN_BYTES + 1))
    binary.write_bytes(b"text\x00more")
    latin.write_bytes("café".encode("latin-1"))
    for path in (big, binary, latin):
        assert read_text_file(path) is None, path
    assert read_text_file(_clean(tmp_path / "repo").parent / "repo" / "LICENSE")


def test_an_em_dash_is_an_error_and_the_line_is_named(tmp_path):
    """Drawn as its own stage because it is the one style rule held at error
    severity rather than warning."""
    found = text_findings(tmp_path, tmp_path / "doc.md", "one\ntwo\nthree " + EM + " four\n")
    assert [(f.rule, f.severity, f.line, f.path) for f in found] == \
        [("em-dash", "error", 3, "doc.md")]


def test_four_files_are_required_and_absence_is_the_whole_finding(tmp_path):
    """The card says the contents are never read. An empty directory raises one
    finding per name, and nothing else names a required file."""
    assert len(REQUIRED_FILES) == 4
    missing = [f for f in scan(tmp_path) if f.rule == "required-file"]
    assert sorted((f.path, f.severity) for f in missing) == \
        sorted((n, "error") for n in REQUIRED_FILES)


def test_five_further_rules_ask_whether_the_surface_is_inspectable(tmp_path):
    """The contract stage. Each is a warning, so an unmigrated repository is
    told about them without being blocked."""
    contract = {"public-changelog", "public-funding", "developer-agent-instructions",
                "developer-usage-doc", "developer-ci-workflow"}
    found = [f for f in scan(tmp_path) if f.rule in contract]
    assert {f.rule for f in found} == contract
    assert {f.severity for f in found} == {"warning"}


def test_the_readme_rules_want_three_things_and_say_so_separately(tmp_path):
    """A README missing its public framing, its developer entry points and a
    real image raises three rules rather than one."""
    (tmp_path / "README.md").write_text("# Demo\n\nnothing here.\n", encoding="utf-8")
    assert _rules(readme_delivery_findings(tmp_path)) == {
        "readme-public-delivery", "readme-developer-delivery", "readme-visual-asset"}
    (tmp_path / "docs" / "brand").mkdir(parents=True)
    (tmp_path / "docs" / "brand" / "hero.png").write_bytes(b"x")
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    assert readme_delivery_findings(tmp_path) == []


def test_each_known_credential_shape_is_matched_by_its_own_rule(tmp_path):
    """Five provider rules are drawn as a group, and secret_rules names them
    plus the generic one. A shape that stopped matching would show up here."""
    assert {rule for rule, _, _ in SECRET_PATTERNS} == set(SHAPES)
    assert secret_rules() == set(SHAPES) | {"secret-assignment"}
    for rule, shape in SHAPES.items():
        found = text_findings(tmp_path, tmp_path / "f.md", "value: " + shape + "\n")
        assert rule in _rules(found), rule


def test_a_span_a_provider_rule_claimed_is_not_counted_twice(tmp_path):
    """First half of the accented row. The generic rule would match this line on
    its own, and the overlap check is what keeps it to one finding."""
    line = 'api_key = "' + SHAPES["github-token"] + '"\n'
    assert _rules(text_findings(tmp_path, tmp_path / "f.md", line)) == {"github-token"}


def test_a_placeholder_is_dropped_and_a_credential_shape_is_not(tmp_path):
    """Second half of the accented row, and the filters stage. Both inputs match
    the generic pattern; only one of them survives to be counted."""
    marked = [f["key"] for f in _card()["fields"] if f.get("tone", "none") != "none"]
    assert marked == ["secret-assignment"]
    for value in ("YOUR_API_KEY_HERE_PLACEHOLDER", "redacted-value-goes-here",
                  "aaaaaaaaaaaaaaaaaa"):
        line = 'client_secret = "' + value + '"\n'
        assert text_findings(tmp_path, tmp_path / "f.md", line) == [], value
    real = 'client_secret = "' + "q7Wm2Zx9Lp4Kd8" + 'Tn6Rv3Bh"\n'
    assert _rules(text_findings(tmp_path, tmp_path / "f.md", real)) == {"secret-assignment"}


def test_the_three_outcomes_are_the_three_the_drawing_names(tmp_path, capsys):
    """Ready, needs polish and blocked, each reached for real, with the exit
    code the outcome note claims."""
    clean = _clean(tmp_path / "clean")
    assert summarize_findings(scan(clean)).status == "ready"
    assert summarize_findings(scan(clean)).score == 100
    assert main([str(clean)]) == 0
    polish = _clean(tmp_path / "polish")
    (polish / "CHANGELOG.md").unlink()
    summary = summarize_findings(scan(polish))
    assert (summary.status, summary.score, summary.errors) == ("needs-polish", 90, 0)
    assert main([str(polish)]) == 0
    blocked = _clean(tmp_path / "blocked")
    (blocked / "NOTES.md").write_text("an " + EM + " em dash\n", encoding="utf-8")
    assert summarize_findings(scan(blocked)).status == "blocked"
    assert main([str(blocked)]) == 1
    capsys.readouterr()


def test_only_a_repository_with_a_github_remote_is_discovered(tmp_path):
    """The remote stage. A local-only checkout is walked past rather than
    reported as unverifiable."""
    _clean(tmp_path / "kept")
    local = tmp_path / "local"
    (local / ".git").mkdir(parents=True)
    (local / ".git" / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
    found = ws.discover_forward_facing_repos([tmp_path])
    assert [p.name for p in found] == ["kept"]


def test_two_checkouts_of_one_remote_collapse_to_the_shallower(tmp_path):
    """The duplicates stage. Both paths carry the same slug, so the matrix has
    to name the repository once."""
    _clean(tmp_path / "primary")
    _clean(tmp_path / "nested" / "deeper" / "mirror")
    found = ws.discover_forward_facing_repos([tmp_path])
    assert [p.name for p in found] == ["primary"]
    assert ws.build_delivery_matrix([tmp_path])["repository_count"] == 1


def test_the_worst_verdict_wins_and_nothing_is_averaged(tmp_path):
    """The status stage. One drifted verdict decides the record even when the
    other two are clean, and a credential shape decides a verdict of its own."""
    assert len(ws.PUBLIC_DELIVERY_RULES) == 6
    assert len(ws.DEVELOPER_DELIVERY_RULES) == 4
    assert len(ws.SECRET_RULE_PREFIXES) == 6
    clean = _clean(tmp_path / "clean")
    assert scan_delivery_surface(clean) == []
    drifted = _clean(tmp_path / "drifted", slug="HarperZ9/other")
    (drifted / "USAGE.md").unlink()
    matrix = ws.build_delivery_matrix([tmp_path])
    records = {r["name"]: r for r in matrix["repositories"]}
    assert records["clean"]["status"] == "MATCH"
    assert [records["drifted"][k] for k in ("status", "public_delivery",
            "developer_delivery", "boundary")] == ["DRIFT", "MATCH", "DRIFT", "MATCH"]
    assert matrix["counts"] == {"MATCH": 1, "DRIFT": 1, "UNVERIFIABLE": 0}


def test_the_matrix_carries_no_local_path_and_no_matched_value(tmp_path):
    """The footnote's claim, checked against the serialized table rather than
    against the boundary flags it sets for itself."""
    root = _clean(tmp_path / "leaky", slug="HarperZ9/leaky")
    (root / "docs" / "config.md").write_text("token: " + SHAPES["slack-token"] + "\n",
                                             encoding="utf-8")
    matrix = ws.build_delivery_matrix([tmp_path])
    record = matrix["repositories"][0]
    assert record["boundary"] == "DRIFT"
    text = json.dumps(matrix)
    assert SHAPES["slack-token"] not in text
    assert str(tmp_path.resolve()) not in text
    assert matrix["privacy_boundary"] == {
        "absolute_paths_included": False, "raw_secret_values_included": False,
        "network_calls_performed": False, "filesystem_writes_performed": False}

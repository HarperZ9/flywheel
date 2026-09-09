"""Offline HTML presentation of recomputed ServiceDesk review evidence."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


def render_review_html(report: dict[str, Any]) -> str:
    verification = report["verification"]
    claimed = report["claimed_outcome"]
    layers = report["evidence_layers"]
    source = report.get("source_version", {})
    return "".join([
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">\n",
        "<title>ServiceDesk incident review</title>\n",
        "<style>body{font-family:Arial,sans-serif;line-height:1.45;margin:2rem;max-width:980px;color:#1b1b1b;overflow-wrap:anywhere}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top}"
        ".table-scroll{max-width:100%;overflow-x:auto}th{background:#f3f3f3}.pass{color:#126b31}.fail{color:#9b1c1c}.muted{color:#555}</style>\n",
        "</head>\n<body>\n",
        "<h1>ServiceDesk incident review</h1>\n",
        "<p class=\"muted\">Local artifact paths are omitted from this portable report.</p>\n",
        "<h2>Claimed outcome</h2>\n",
        f"<p>Recorded cases passed: {_yn(claimed.get('all_recorded_cases_passed'))}; "
        f"recorded failed cases: {_e(', '.join(claimed.get('recorded_failed_case_ids', [])) or 'none')}; "
        f"calibration false accepts recorded: {_e(claimed.get('calibration_false_accepts', 'unknown'))}.</p>\n",
        "<h2>Recomputed outcome</h2>\n",
        f"<p class=\"{_state_class(verification['observed_state'])}\">State: {_e(verification['observed_state'])}; "
        f"failure codes: {_e(', '.join(verification['failure_codes']) or 'none')}.</p>\n",
        "<h2>Evidence layers</h2>\n",
        _layer_html("Source integrity", layers["source_integrity"]),
        _layer_html("Synthetic task check", layers["synthetic_task_check"]),
        _layer_html("Record consistency", layers["record_consistency"]),
        f"<p><strong>Externally trusted evidence:</strong> {_e(layers['externally_trusted_evidence']['observed_state'])}. "
        f"{_e(layers['externally_trusted_evidence']['reason'])}</p>\n",
        "<h2>Integrity checks</h2>\n",
        _checks_table(layers["source_integrity"].get("checks", [])),
        "<h2>Recorded case results</h2>\n",
        _cases_table(report.get("cases", [])),
        "<h2>Calibration</h2>\n",
        _calibration_html(report.get("calibration", {})),
        "<h2>Source version</h2>\n",
        f"<p>Manifest created: {_e(source.get('created_at_utc', 'unknown'))}; "
        f"manifest sha256: {_e(source.get('source_manifest_sha256', 'unknown'))}.</p>\n",
        _source_entries_table(source.get("entries", [])),
        "<h2>Limits</h2>\n<ul>\n",
        *[f"<li>{_e(item)}</li>\n" for item in report.get("limits", [])],
        "</ul>\n</body>\n</html>\n",
    ])


def write_review_html(report: dict[str, Any], out_path: Path) -> None:
    target = Path(out_path)
    artifact = Path(report["artifact_dir"]).resolve()
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(artifact)
    except ValueError:
        pass
    else:
        raise ValueError("html_output_inside_artifact_dir")
    if target.exists():
        raise ValueError("html_output_already_exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="") as stream:
        stream.write(render_review_html(report))


def _layer_html(title: str, layer: dict[str, Any]) -> str:
    return (
        f"<h3>{_e(title)}</h3>\n"
        f"<p class=\"{_state_class(layer.get('observed_state', 'fail'))}\">State: {_e(layer.get('observed_state', 'fail'))}; "
        f"failure codes: {_e(', '.join(layer.get('failure_codes', [])) or 'none')}.</p>\n"
        f"<p>Basis: {_e(layer.get('basis', 'local artifact checks'))}.</p>\n"
        "<ul>\n"
        + "".join(f"<li>{_e(item)}</li>\n" for item in layer.get("does_not_prove", []))
        + "</ul>\n"
    )


def _checks_table(checks: list[dict[str, Any]]) -> str:
    rows = ["<div class=\"table-scroll\" tabindex=\"0\" role=\"region\" aria-label=\"Scrollable evidence table\"><table><tr><th>Check</th><th>State</th><th>Failure code</th><th>Claimed</th><th>Recomputed</th></tr>\n"]
    for row in checks:
        rows.append(f"<tr><td>{_e(row.get('id'))}</td><td>{_e(row.get('observed_state'))}</td><td>{_e(row.get('failure_code') or '')}</td><td>{_e(row.get('claimed'))}</td><td>{_e(row.get('recomputed'))}</td></tr>\n")
    rows.append("</table></div>\n")
    return "".join(rows)


def _cases_table(cases: list[dict[str, Any]]) -> str:
    rows = ["<div class=\"table-scroll\" tabindex=\"0\" role=\"region\" aria-label=\"Scrollable evidence table\"><table><tr><th>Case</th><th>Recorded state</th><th>Failure codes</th><th>Basis</th></tr>\n"]
    for row in cases:
        state = "pass" if row.get("passed") is True else "fail"
        rows.append(f"<tr><td>{_e(row.get('case_id'))}</td><td>{_e(state)}</td><td>{_e(', '.join(row.get('failure_codes', [])))}</td><td>{_e(row.get('evidence_basis', 'recorded'))}</td></tr>\n")
    rows.append("</table></div>\n<p>Recorded case flags are not rerun by this review.</p>\n")
    return "".join(rows)


def _calibration_html(calibration: dict[str, Any]) -> str:
    rows = [f"<p>State: {_e(calibration.get('observed_state', 'fail'))}; false accepts: {_e(calibration.get('false_accepts', 'unknown'))}; basis: {_e(calibration.get('basis', 'unknown'))}.</p>\n"]
    rows.append("<div class=\"table-scroll\" tabindex=\"0\" role=\"region\" aria-label=\"Scrollable evidence table\"><table><tr><th>Calibration case</th><th>Expected</th><th>Observed</th><th>Failure codes</th></tr>\n")
    for row in calibration.get("case_results", []):
        rows.append(f"<tr><td>{_e(row.get('case_id'))}</td><td>{_e(row.get('expected_state'))}</td><td>{_e(row.get('observed_state'))}</td><td>{_e(', '.join(row.get('failure_codes', [])))}</td></tr>\n")
    rows.append("</table></div>\n")
    return "".join(rows)


def _source_entries_table(entries: list[dict[str, Any]]) -> str:
    rows = ["<div class=\"table-scroll\" tabindex=\"0\" role=\"region\" aria-label=\"Scrollable evidence table\"><table><tr><th>Source id</th><th>Retrieved</th><th>Body sha256</th><th>Body stored</th><th>Used for</th></tr>\n"]
    for row in entries:
        rows.append(f"<tr><td>{_e(row.get('id'))}</td><td>{_e(row.get('retrieved_at_utc'))}</td><td>{_e(row.get('body_sha256'))}</td><td>{_e(row.get('body_stored'))}</td><td>{_e(', '.join(row.get('used_for', [])))}</td></tr>\n")
    rows.append("</table></div>\n")
    return "".join(rows)


def _e(value: Any) -> str:
    text = str(value)
    # Portable presentation is deliberately lossy; machine JSON retains local data.
    text = re.sub(r"(?i)\b(?:authorization\s*[:=]\s*)?bearer\s+[^\s<>]+", "[credential redacted]", text)
    text = re.sub(r"(?i)[\"']?(?:api[_-]?key|token|password|secret)[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s<>]+)", "[credential redacted]", text)
    text = re.sub(r"(?:[A-Za-z]:[\\/]|\\\\)[^\s<>\"']+", "[local path redacted]", text)
    text = re.sub(r"(?<![\w:/<])/(?!/)[^\s<>\"']+", "[local path redacted]", text)
    return html.escape(text, quote=True)


def _yn(value: Any) -> str:
    return "yes" if value is True else "no"


def _state_class(value: str) -> str:
    return "pass" if value == "pass" else "fail"

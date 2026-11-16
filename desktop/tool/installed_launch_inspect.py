"""Installed Inspect import/reopen acceptance phase helpers."""
from __future__ import annotations

import hashlib, json, re, sqlite3, sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.evidence_json import canonical_bytes
from harness.inspect_upload_metadata import inspect_data_ref
from harness.journey_store import JourneyStore, MutationCommand
from harness.operation_grants import load_or_create_owner_ref

try:
    from .installed_launch_inspect_contract import INSPECT_ASSERTION_IDS
except ImportError:
    from installed_launch_inspect_contract import INSPECT_ASSERTION_IDS  # type: ignore

H21, H22, H23, H24, H25, H26, H27, H28, H29 = INSPECT_ASSERTION_IDS


def inspect_not_checked(harness, severity="info") -> None:
    for aid in INSPECT_ASSERTION_IDS:
        harness._add(aid, "NOT_CHECKED", severity)


def inspect_before_restart(harness, port: int, token: str | None, env: dict[str, str]) -> dict | None:
    if not getattr(harness.c, "inspect_import", False):
        return None
    _api_only(harness)
    if not token:
        for aid in (H21, H22, H23, H24, H25):
            harness._add(aid, "AUTH_TOKEN_UNAVAILABLE")
        return None
    try:
        raw, sha, length, filename = _fixture(harness)
        harness._add(H21, "PASS", observed={"sha256": sha, "byte_length": length, "filename": filename})
        home = Path(env["FLYWHEEL_HOME"])
        journey_ref, head = _seed_journey(home, harness.c.run_id, harness.clock.now())
        harness._add(H22, "PASS", observed={"owner_ref_present": True, "journey_ref": journey_ref})
        prep = _prepare(harness, port, token, sha, length, filename, journey_ref, head)
        grant_ref = _approve(harness, port, token, prep)
        bound, binding = _proposal_bound(prep, grant_ref, sha)
        harness._add(H23, "PASS" if bound else "FAIL", observed=binding)
        if not bound:
            _remaining_before_fail(harness)
            return None
        headers = _headers(prep, grant_ref, sha, length, filename)
        code, uploaded = harness.http.post_bytes(f"http://127.0.0.1:{port}/api/import/inspect", raw, headers, token)
        upload_ok = _upload_ok(code, uploaded, sha, length, filename)
        harness._add(H24, "PASS" if upload_ok else "FAIL", observed=_upload_observed(code, uploaded))
        if not upload_ok:
            harness._add(H25, "NOT_CHECKED")
            return None
        controls = _controls(harness, port, token, raw, sha, length, filename, journey_ref, head, headers, uploaded["stored"]["eid"])
        harness._add(H25, "PASS" if _controls_ok(controls) else "FAIL", observed=controls)
        return {"eid": uploaded["stored"]["eid"], "uploaded": uploaded, "home": home, "owner": load_or_create_owner_ref(home)}
    except Exception as exc:
        pending = [aid for aid in (H21, H22, H23, H24, H25) if not _has_row(harness, aid)]
        if pending:
            harness._add(pending[0], "FAIL", observed={"error": type(exc).__name__})
            for aid in pending[1:]:
                harness._add(aid, "NOT_CHECKED")
        return None


def inspect_after_restart(harness, port: int, token: str | None, ctx: dict | None) -> None:
    if not getattr(harness.c, "inspect_import", False):
        return
    if not token or not ctx:
        for aid in (H26, H27, H28):
            harness._add(aid, "NOT_CHECKED")
        return
    code, reopened = harness.http.get_json(f"http://127.0.0.1:{port}/api/import/inspect/{ctx['eid']}", token)
    match = code == 200 and reopened == ctx["uploaded"]
    harness._add(H26, "PASS" if match else "FAIL", observed={"status_code": code, "exact_match": match})
    code, listed = harness.http.get_json(f"http://127.0.0.1:{port}/api/import/inspect?limit=1", token)
    items = listed.get("items", []) if isinstance(listed, dict) else []
    row = items[0] if items else {}
    listed_ok = code == 200 and row.get("eid") == ctx["eid"] and "report" not in row
    harness._add(H27, "PASS" if listed_ok else "FAIL", observed={"status_code": code, "eid_listed": row.get("eid") == ctx["eid"], "report_omitted": "report" not in row})
    tampered = _tamper(ctx["home"], ctx["owner"], ctx["eid"])
    code, body = harness.http.get_json(f"http://127.0.0.1:{port}/api/import/inspect/{ctx['eid']}", token)
    err = body.get("error", {}).get("code") if isinstance(body, dict) else None
    harness._add(H28, "PASS" if tampered and code == 409 and err == "STORE_TAMPERED" else "FAIL", observed={"tampered": tampered, "status_code": code, "error_code": err})


def _api_only(harness) -> None:
    harness._add(H29, "PASS", observed={"api_only": True, "native_ui_launched": False, "desktop_file_picker_exercised": False})


def _fixture(harness) -> tuple[bytes, str, int, str]:
    path = Path(harness.c.inspect_fixture) if harness.c.inspect_fixture else Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "inspect" / "v1" / "single-success.fixture.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    raw = canonical_bytes(body.get("inspect_log", body))
    return raw, hashlib.sha256(raw).hexdigest(), len(raw), path.name


def _seed_journey(home: Path, run_id: str, now: str) -> tuple[str, str]:
    owner = load_or_create_owner_ref(home)
    digest = hashlib.sha256(f"{run_id}:{owner}".encode()).hexdigest()
    journey = "jrn_" + digest[:32]
    body = {"legacy_label": f"{run_id}-inspect-journey", "goal": "installed inspect acceptance", "intake": {}, "occurred_at": now}
    ack = JourneyStore(home / "state").create(MutationCommand(owner, journey, None, f"{run_id}-inspect-journey", "intake", body))
    return journey, ack.event_head_sha256


def _prepare(harness, port: int, token: str, sha: str, length: int, filename: str, journey: str, head: str, suffix: str = "inspect-import") -> dict:
    body = {"schema": "flywheel.gateway-operation/v1", "journey_ref": journey, "expected_event_head": head, "client_request_id": f"{harness.c.run_id}-{suffix}", "operation": {"source": {"kind": "client-upload", "format": "inspect-json", "sha256": sha, "byte_length": length, "filename": filename}, "data_refs": [inspect_data_ref(sha)], "credential_refs": []}}
    code, response = harness.http.post_json(f"http://127.0.0.1:{port}/api/gateway-grants/prepare/import.inspect", body, token)
    return response if code == 200 and isinstance(response, dict) else {}


def _approve(harness, port: int, token: str, proposal: dict) -> str:
    code, body = harness.http.post_json(f"http://127.0.0.1:{port}/api/gateway-grants/approve-once", {"proposal_ref": proposal.get("proposal_ref")}, token)
    return str(body.get("grant_ref", "")) if code == 200 and isinstance(body, dict) else ""


def _headers(proposal: dict, grant_ref: str, sha: str, length: int, filename: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "Content-Length": str(length), "X-Flywheel-Journey-Ref": proposal["journey_ref"], "X-Flywheel-Expected-Event-Head": proposal["expected_event_head"], "X-Flywheel-Client-Request-Id": proposal["client_request_id"], "X-Flywheel-Grant-Ref": grant_ref, "X-Flywheel-Inspect-Sha256": sha, "X-Flywheel-Inspect-Byte-Length": str(length), "X-Flywheel-Inspect-Filename": filename}


def _upload_ok(code: int, body: Any, sha: str, length: int, filename: str) -> bool:
    if code != 200 or not isinstance(body, dict):
        return False
    source, report = body.get("source", {}), body.get("report", {})
    return (body.get("schema") == "flywheel.inspect-import-result/v1"
            and source.get("format") == "inspect-json"
            and source.get("sha256") == sha and source.get("byte_length") == length
            and source.get("filename") == filename
            and body.get("data_ref") == inspect_data_ref(sha)
            and isinstance(report, dict)
            and report.get("schema") == "flywheel.inspect-evidence/v1"
            and report.get("source", {}).get("sha256") == sha
            and report.get("source", {}).get("byte_length") == length
            and report.get("producer", {}).get("format") == "inspect-json"
            and report.get("producer", {}).get("version") == 2
            and report.get("reported_status") == "success"
            and report.get("assessment") == "reported"
            and report.get("invalidated") is False
            and report.get("semantic_verification") == "UNVERIFIABLE"
            and bool(body.get("stored", {}).get("eid")))


def _upload_observed(code: int, body: Any) -> dict:
    return {"status_code": code, "schema": body.get("schema") if isinstance(body, dict) else None, "eid_present": bool(body.get("stored", {}).get("eid")) if isinstance(body, dict) else False, "reported_status": body.get("report", {}).get("reported_status") if isinstance(body, dict) else None, "semantic_verification": body.get("report", {}).get("semantic_verification") if isinstance(body, dict) else None}


def _controls(harness, port: int, token: str, raw: bytes, sha: str, length: int, filename: str, journey: str, head: str, headers: dict[str, str], expected_eid: str) -> dict:
    code, body = harness.http.get_json(f"http://127.0.0.1:{port}/api/import/inspect", None)
    missing_bearer_code = _error_code(body)
    missing_bearer = code == 401 and missing_bearer_code == "AUTH_REQUIRED"
    bad_grant = dict(headers); bad_grant["X-Flywheel-Grant-Ref"] = "gnt_" + "f" * 32
    code, body = harness.http.post_bytes(f"http://127.0.0.1:{port}/api/import/inspect", raw, bad_grant, token)
    missing_grant_code = _error_code(body)
    missing_grant = code == 403 and missing_grant_code == "PERMISSION_REQUIRED"
    before_eids = _list_eids(harness, port, token)
    prep = _prepare(harness, port, token, sha, length, filename, journey, head, "inspect-changed-control")
    grant_ref = _approve(harness, port, token, prep)
    fresh_bound, _ = _proposal_bound(prep, grant_ref, sha)
    changed_headers = _headers(prep, grant_ref, sha, length, filename) if fresh_bound else {}
    changed = _same_length_changed(raw)
    code, body = ((0, {}) if not fresh_bound else harness.http.post_bytes(f"http://127.0.0.1:{port}/api/import/inspect", changed, changed_headers, token))
    changed_code = _error_code(body)
    after_eids = _list_eids(harness, port, token)
    changed_source = code == 409 and changed_code == "SOURCE_DIGEST_MISMATCH"
    fresh_single = before_eids == (expected_eid,)
    no_new_store = fresh_single and before_eids == after_eids
    return {"missing_bearer_rejected": missing_bearer, "missing_bearer_error_code": missing_bearer_code,
            "missing_grant_rejected": missing_grant, "missing_grant_error_code": missing_grant_code,
            "fresh_changed_grant_bound": fresh_bound, "changed_source_rejected": changed_source,
            "changed_source_error_code": changed_code, "fresh_single_uploaded_row_before_changed_source": fresh_single,
            "no_new_store_row_after_changed_source": no_new_store,
            "store_eids_before_changed_source": list(before_eids) if before_eids is not None else None,
            "store_eids_after_changed_source": list(after_eids) if after_eids is not None else None}


def _proposal_bound(proposal: dict, grant_ref: str, sha: str) -> tuple[bool, dict]:
    expected_ref = inspect_data_ref(sha)
    expected_destination = {"kind": "import", "ref": f"inspect-json:{sha[:16]}"}
    observed = {
        "proposal_present": bool(proposal),
        "grant_present": bool(grant_ref),
        "schema": proposal.get("schema") if isinstance(proposal, dict) else None,
        "action": proposal.get("action") if isinstance(proposal, dict) else None,
        "data_refs_match": isinstance(proposal, dict) and proposal.get("data_refs") == [expected_ref],
        "destination_match": isinstance(proposal, dict) and proposal.get("destination") == expected_destination,
        "planned_grant_match": isinstance(proposal, dict) and grant_ref == proposal.get("planned_grant_ref"),
        "operation_digest_valid": isinstance(proposal, dict) and _valid_sha256(proposal.get("operation_sha256")),
        "arguments_digest_valid": isinstance(proposal, dict) and _valid_sha256(proposal.get("arguments_sha256")),
    }
    ok = (observed["proposal_present"] and observed["grant_present"]
          and observed["schema"] == "flywheel.gateway-grant-proposal/v1"
          and observed["action"] == "import.inspect"
          and observed["data_refs_match"] and observed["destination_match"]
          and observed["planned_grant_match"]
          and observed["operation_digest_valid"]
          and observed["arguments_digest_valid"])
    observed["source_bound"] = bool(ok)
    return bool(ok), observed


def _controls_ok(controls: dict) -> bool:
    keys = ("missing_bearer_rejected", "missing_grant_rejected",
            "fresh_changed_grant_bound", "changed_source_rejected",
            "fresh_single_uploaded_row_before_changed_source",
            "no_new_store_row_after_changed_source")
    return all(controls.get(key) is True for key in keys)


def _error_code(body: Any) -> str | None:
    return body.get("error", {}).get("code") if isinstance(body, dict) else None


def _list_eids(harness, port: int, token: str | None) -> tuple[str, ...] | None:
    eids: list[str] = []
    limit = 50
    for offset in range(0, 256, limit):
        code, body = harness.http.get_json(f"http://127.0.0.1:{port}/api/import/inspect?limit={limit}&offset={offset}", token)
        items = body.get("items") if code == 200 and isinstance(body, dict) else None
        if not isinstance(items, list):
            return None
        for item in items:
            eid = item.get("eid") if isinstance(item, dict) else None
            if type(eid) is not str or not eid:
                return None
            eids.append(eid)
        if len(items) < limit:
            return tuple(eids)
    return None


_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


def _valid_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _same_length_changed(raw: bytes) -> bytes:
    if not raw:
        return raw
    replacement = b"0" if raw[:1] != b"0" else b"1"
    return replacement + raw[1:]


def _remaining_before_fail(harness) -> None:
    for aid in (H24, H25):
        harness._add(aid, "NOT_CHECKED")


def _tamper(home: Path, owner: str, eid: str) -> bool:
    db = home / "state" / "inspect-evidence" / owner / "store.db"
    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute("SELECT data FROM entities WHERE eid=?", (eid,)).fetchone()
            data = json.loads(row[0]); data["result"]["source"]["sha256"] = "0" * 64
            conn.execute("UPDATE entities SET data=? WHERE eid=?", (json.dumps(data), eid))
        return True
    except Exception:
        return False


def _has_row(harness, aid: str) -> bool:
    return any(row.get("id") == aid for row in harness.rows)

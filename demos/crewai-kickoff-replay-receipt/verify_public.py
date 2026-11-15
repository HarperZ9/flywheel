"""Verify this public-safe CrewAI replay audit bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parent
checks = 0


def public_files() -> list[Path]:
    """Return bundle files while ignoring local version-control metadata."""
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts
    ]


def require(condition: bool, message: str) -> None:
    """Count and enforce one condition."""
    global checks
    checks += 1
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    """Return a file's SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nested_value(document: dict[str, Any], dotted_path: str) -> Any:
    """Resolve a dotted object path."""
    current: Any = document
    for part in dotted_path.split("."):
        require(isinstance(current, dict) and part in current, f"missing {dotted_path}")
        current = current[part]
    return current


canonical = json.loads((ROOT / "canonical-result.json").read_text(encoding="utf-8"))
receipt = json.loads((ROOT / "action-receipt.json").read_text(encoding="utf-8"))

require(
    canonical["schema"] == "crewai.kickoff-for-each-replay-audit-public/v1",
    "wrong canonical schema",
)
require(
    receipt["schema"] == "project-telos.action-receipt/v1",
    "wrong receipt schema",
)
require(
    canonical["publication_state"] == "public_safe_evidence_export",
    "wrong publication state",
)

required_fields = [
    "action_id",
    "action_intent_id",
    "event_id",
    "event_type",
    "idempotency_key",
    "action.kind",
    "intent_ref",
    "authority_ref",
    "execution_ref",
    "evidence_ref",
    "review_ref",
    "compensation_ref",
    "trace.span_ref",
    "execution.external_request_id",
    "execution.idempotency_key",
    "execution.terminal_status",
    "execution.redacted_before_ref",
    "execution.redacted_after_ref",
    "agent.principal",
    "component.name",
    "component.version",
    "component.config_hash",
    "input_materials[].digest",
    "input_materials[].ref",
    "side_effect.class",
    "policy.decision",
    "policy.ref",
    "verification.verdict",
    "result.state",
    "result.stop_reason",
    "retry.attempt",
    "retry.max_attempts",
    "receipts[].hash",
    "persistence.append_only",
    "created_at",
]
for field in required_fields:
    if "[]." in field:
        collection_path, item_field = field.split("[].", 1)
        collection = nested_value(receipt, collection_path)
        require(isinstance(collection, list) and collection, f"empty {collection_path}")
        for item in collection:
            value = nested_value(item, item_field)
            require(value not in (None, ""), f"empty {field}")
    else:
        value = nested_value(receipt, field)
        if field != "compensation_ref":
            require(value not in (None, ""), f"empty {field}")

require(receipt["side_effect"]["class"] == "read", "wrong side-effect class")
require(receipt["policy"]["decision"] == "allow", "wrong policy decision")
require(receipt["verification"]["verdict"] == "DRIFT", "wrong verification verdict")
require(receipt["verification"]["candidate_verdict"] == "MATCH", "wrong candidate verdict")
require(receipt["result"]["state"] == "completed", "wrong result state")
require(receipt["result"]["stop_reason"] == "completed", "wrong stop reason")
require(receipt["persistence"]["append_only"] is True, "receipt is not append-only")
require(
    receipt["trace"]["receipt_is_trace_span"] is False,
    "receipt incorrectly collapsed into a trace span",
)

canonical_digest = sha256(ROOT / "canonical-result.json")
require(
    receipt["execution"]["result_hash"] == f"sha256:{canonical_digest}",
    "canonical execution hash drift",
)
require(
    receipt["receipts"][0]["hash"] == f"sha256:{canonical_digest}",
    "canonical receipt hash drift",
)
require(
    receipt["input_materials"][0]["digest"] == f"sha256:{canonical_digest}",
    "canonical input hash drift",
)

for material in canonical["bundle_materials"]:
    require(
        material["digest"] == f"sha256:{sha256(ROOT / material['ref'])}",
        f"bundle material drift: {material['ref']}",
    )

for phase in ("regression", "control", "combined"):
    evidence = canonical["results"]["unmodified"][phase]
    require(
        evidence["digest"] == f"sha256:{sha256(ROOT / evidence['ref'])}",
        f"unmodified evidence drift: {phase}",
    )

for phase in (
    "regression",
    "combined",
    "existing_kickoff_for_each",
    "existing_replay",
    "static_verification",
):
    evidence = canonical["results"]["candidate"][phase]
    require(
        evidence["digest"] == f"sha256:{sha256(ROOT / evidence['ref'])}",
        f"candidate evidence drift: {phase}",
    )

manifest: dict[str, str] = {}
for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
    require(match is not None, f"malformed manifest line: {line}")
    assert match is not None
    manifest[match.group(2)] = match.group(1)

payload_files = {
    path.relative_to(ROOT).as_posix()
    for path in public_files()
    if path.is_file() and path.name != "SHA256SUMS"
}
require(set(manifest) == payload_files, "manifest does not cover every public file")
for relative_path, expected_digest in manifest.items():
    require(
        sha256(ROOT / relative_path) == expected_digest,
        f"manifest drift: {relative_path}",
    )

test_bytes = (ROOT / "test_kickoff_for_each_replay.py").read_bytes()
patch_text = (ROOT / "candidate.patch").read_text(encoding="utf-8")
require(
    hashlib.sha256(test_bytes).hexdigest()
    == "9e0aa13b3aabda3363fbc58f17626674ea558420612e656b56ad8ebd14b89240",
    "regression test drift",
)
require(
    patch_text.count("-        self._task_output_handler.reset()") == 1,
    "candidate production deletion missing or duplicated",
)
require(
    "test_kickoff_for_each_persists_only_the_most_recent_run_for_replay"
    in patch_text,
    "candidate regression missing",
)

banned_patterns = {
    "windows_absolute_path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"),
    "unix_user_path": re.compile(r"/(?:Users|home|root)/", re.IGNORECASE),
    "workspace_path": re.compile("C" + r":[\\/]dev", re.IGNORECASE),
    "operator_name": re.compile("Za" + "in", re.IGNORECASE),
    "private_key": re.compile("BEGIN " + "PRIVATE KEY"),
    "openai_key": re.compile("OPENAI_" + "API_KEY", re.IGNORECASE),
    "anthropic_key": re.compile("ANTHROPIC_" + "API_KEY", re.IGNORECASE),
    "github_token": re.compile(
        "(?:gh" + "p_|github_" + "pat_)[A-Za-z0-9_]+"
    ),
    "bearer_token": re.compile("Bear" + "er " + r"[A-Za-z0-9._-]{12,}"),
}
for path in public_files():
    text = path.read_text(encoding="utf-8", errors="replace")
    for name, pattern in banned_patterns.items():
        require(pattern.search(text) is None, f"{name} leak in {path.name}")

public_text = "\n".join(
    path.read_text(encoding="utf-8", errors="replace")
    for path in public_files()
)
require(
    ("un" + "published") not in public_text.lower(),
    "non-durable publication wording",
)
require(
    ("after two " + "kickoff_for_each runs") not in public_text,
    "incorrect two-call wording",
)

print("verification=MATCH")
print(f"checks={checks}")
print(f"canonical_sha256={canonical_digest}")
print(f"action_receipt_sha256={sha256(ROOT / 'action-receipt.json')}")
print(f"files={len(payload_files)}")
print("local_path_leaks=0")
print("secret_pattern_matches=0")

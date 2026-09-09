"""Bounded, read-only admission of one pinned Norvane JSON capture."""
from __future__ import annotations

import hashlib

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .private_artifact_fs import NOT_FOUND, PrivateArtifactError, open_artifact_root

SOURCE_COMMIT = "56fd0c11e6cb973b9e1f752ba7c1f35ec3f570bb"
MANIFEST_SCHEMA = "flywheel.norvane-capture-source/v1"
MAX_FILE, MAX_TOTAL, MAX_LAST_STEP = 1_048_576, 8_388_608, 33
STATE_KEYS = {"step", "commands_executed", "test_invocations", "submitted_report",
              "fix_correct", "fix_check_output", "forced_submit", "tests_modified",
              "mock_package_paths"}
SCORE_KEYS = (STATE_KEYS - {"step", "commands_executed"}) | {
    "steps", "num_commands", "num_test_invocations", "num_test_invocations_passed"}


def require(condition):
    if not condition:
        raise ValueError("capture input rejected")


def digest(value):
    require(type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))
    return value


def integer(value, maximum=256):
    require(type(value) is int and 0 <= value <= maximum)


def declaration(value, expected):
    # Snapshot caller-owned data with the existing strict JSON boundary.
    value = strict_load_json(canonical_bytes(value), max_bytes=65_536, max_depth=4)
    require(type(value) is dict and set(value) == {
        "schema", "source_commit", "last_step", "files"})
    require(value["schema"] == MANIFEST_SCHEMA and value["source_commit"] == SOURCE_COMMIT)
    integer(value["last_step"], MAX_LAST_STEP)
    require(value["last_step"] >= 2)
    names = [f"step-{i}/{kind}.json" for i in range(2, value["last_step"] + 1)
             for kind in ("state", "messages")] + ["final/score.json"]
    require(type(value["files"]) is dict and set(value["files"]) <= set(names))
    for item in value["files"].values():
        digest(item)
    if expected is not None:
        digest(expected)
    anchor = ("unavailable" if expected is None else
              "match" if canonical_sha256(value) == expected else "mismatch")
    return value, names, anchor


def _commands(rows, output):
    require(type(rows) is list and len(rows) <= 256)
    for row in rows:
        require(type(row) is dict and set(row) ==
                ({"command", "return_code", "output"} if output else {"command", "return_code"}))
        require(type(row["command"]) is str and len(row["command"]) <= 65_536)
        require(type(row["return_code"]) is int and -2**31 <= row["return_code"] < 2**31)
        if output:
            require(type(row["output"]) is str and len(row["output"]) <= 2000)


def validate_native(name, value):
    if name.endswith("messages.json"):
        require(type(value) is list and len(value) <= 4096)
        for message in value:
            require(type(message) is dict and type(message.get("role")) is str
                    and message["role"] in ("system", "user", "assistant", "tool", "developer"))
        return
    score = name == "final/score.json"
    require(type(value) is dict and set(value) == (SCORE_KEYS if score else STATE_KEYS))
    integer(value["steps" if score else "step"], MAX_LAST_STEP + 1)
    for key in ("submitted_report", "fix_check_output"):
        require(value[key] is None or type(value[key]) is str)
    for key in ("fix_correct", "tests_modified"):
        require(value[key] is None or type(value[key]) is bool)
    require(type(value["forced_submit"]) is bool)
    require(type(value["mock_package_paths"]) is list and len(value["mock_package_paths"]) <= 256)
    require(all(type(path) is str for path in value["mock_package_paths"]))
    _commands(value["test_invocations"], False)
    if score:
        for key in ("num_commands", "num_test_invocations", "num_test_invocations_passed"):
            integer(value[key])
    else:
        _commands(value["commands_executed"], True)
        require(value["step"] == int(name.split("/")[0][5:]))


def read_capture(root, manifest, expected=None):
    """Read only fixed JSON names with existing handle-relative filesystem custody."""
    manifest, names, anchor = declaration(manifest, expected)
    parsed, inventory, missing, mismatches, total = {}, [], [], [], 0
    with open_artifact_root(root, writable=False) as reader:
        for name in names:
            try:
                raw = reader.read_bytes(name, max_bytes=min(MAX_FILE, MAX_TOTAL - total))
            except PrivateArtifactError as exc:
                if exc.code != NOT_FOUND:
                    raise
                missing.append(name)
                continue
            total += len(raw)
            # Native transcripts are arrays; the shared parser admits objects.
            if name.endswith("messages.json"):
                envelope = strict_load_json(b'{"messages":' + raw + b'}',
                    max_bytes=MAX_FILE + 16, max_depth=25)
                require(set(envelope) == {"messages"})
                value = envelope["messages"]
            else:
                value = strict_load_json(raw, max_bytes=MAX_FILE, max_depth=24)
            validate_native(name, value)
            sha = hashlib.sha256(raw).hexdigest()
            inventory.append({"path": name, "sha256": sha, "bytes": len(raw)})
            if name in manifest["files"] and manifest["files"][name] != sha:
                mismatches.append(name)
            parsed[name] = value
    unbound = sorted(set(names) - set(manifest["files"]))
    consistency = "mismatch" if mismatches else "unavailable" if missing or unbound else "match"
    integrity = ("mismatch" if mismatches or anchor == "mismatch" else
                 "match" if consistency == anchor == "match" else "unavailable")
    return manifest, parsed, inventory, missing, unbound, consistency, integrity, anchor

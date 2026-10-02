"""Check restricted Articulate stdio in a built gateway, without model calls.

Two bounded Windows Job sessions check host editing and numeric preservation.
This is frozen command acceptance, not installed-client or global egress proof.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.frozen_mcp_process import run_mcp_process

TOOLS = {"check", "score", "judge", "fix", "polish", "edit_plan", "edit_submit",
         "articulate.status", "articulate.doctor"}
BACKENDS = ("anthropic", "openai", "claude-cli", "sampling", "ollama")
SOURCE = "The sample contains 14 records."
GOOD = "The sample has 14 records."
BAD = "The sample contains 15 records."
ARGS = ["--bundled-lane-mcp", "articulate", "--local-only"]


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def _unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "JSON_DUPLICATE_KEY")
        out[key] = value
    return out


def _json(text):
    try:
        return json.loads(text, object_pairs_hook=_unique,
                          parse_constant=lambda _v: require(False, "JSON_NONFINITE"))
    except (ValueError, TypeError):
        raise RuntimeError("JSON_INVALID") from None


def parse_replies(output, expected_ids):
    replies = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        row = _json(line)
        require(isinstance(row, dict) and set(row) == {"jsonrpc", "id", "result"},
                "REPLY_SHAPE_OR_UNSOLICITED_REQUEST")
        rid = row["id"]
        require(row["jsonrpc"] == "2.0" and type(rid) is int and rid in expected_ids,
                "REPLY_ID_OR_PROTOCOL")
        require(rid not in replies, "REPLY_DUPLICATE")
        require(isinstance(row["result"], dict), "RESULT_SHAPE")
        replies[rid] = row["result"]
    require(set(replies) == expected_ids, "REPLY_MISSING")
    return replies


def _payload(result, *, refused=False):
    require(result.get("isError", False) is refused, "TOOL_ERROR_FLAG")
    content = result.get("content")
    require(isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
            and content[0].get("type") == "text", "TOOL_CONTENT")
    payload = _json(content[0].get("text"))
    require(isinstance(payload, dict), "TOOL_PAYLOAD")
    if "structuredContent" in result:
        require(result["structuredContent"] == payload, "TOOL_CONTENT_CONFLICT")
    return payload


def _initialize(result, version):
    require(result.get("protocolVersion") == "2025-06-18", "PROTOCOL_VERSION")
    require(result.get("serverInfo") == {"name": "articulate", "version": version},
            "SERVER_VERSION_OR_IDENTITY")


def validate_initial(replies, version):
    _initialize(replies[1], version)
    tools = replies[2].get("tools")
    require(isinstance(tools, list) and len(tools) == len(TOOLS)
            and all(isinstance(t, dict) for t in tools), "TOOLS_SHAPE")
    require({t.get("name") for t in tools} == TOOLS, "TOOLS_SET")
    for tool in tools:
        hints = tool.get("annotations", {})
        require(all(hints.get(k) is v for k, v in {
            "openWorldHint": False, "readOnlyHint": True,
            "destructiveHint": False, "idempotentHint": True}.items()), "TOOLS_NOT_LOCAL")
    doctor = _payload(replies[3])
    require(all(doctor.get(k) == v for k, v in {"version": version, "tool_set": "local",
            "editor_default": "host"}.items()), "DOCTOR_PROFILE")
    require(all(doctor.get(k) is True for k in ("ok", "local_only_switch", "offline_editors",
                                              "sampling_advertised")), "DOCTOR_SWITCHES")
    rid = 4
    for name in ("judge", "fix", "polish"):
        for backend in BACKENDS:
            value = _payload(replies[rid], refused=True)
            require(value.get("ok") is False and value.get("error") ==
                    f"{name} backend '{backend}' is not available in local-only mode",
                    "BACKEND_NOT_REFUSED_LOCALLY")
            rid += 1
    for rid in (19, 20):
        plan = _payload(replies[rid])
        require(plan.get("ok") is True and plan.get("backend") == "host"
                and plan.get("status") == "host_edit_required"
                and plan.get("text") == SOURCE and plan.get("attempts") == []
                and plan.get("quality_status") == "unassessed", "HOST_PLAN_INVALID")
        require(isinstance(plan.get("plan_id"), str) and bool(plan["plan_id"])
                and isinstance(plan.get("masked_text"), str)
                and "contains" in plan["masked_text"], "HOST_PLAN_MISSING")
    return _payload(replies[19])


def validate_submissions(replies, version):
    _initialize(replies[1], version)
    for rid, expected_text in ((2, GOOD), (3, SOURCE)):
        value = _payload(replies[rid])
        require(value.get("ok") is True and value.get("backend") == "host"
                and value.get("text") == expected_text, "SUBMIT_TEXT")
        refused = value.get("refused")
        require(isinstance(refused, list) and (not refused if rid == 2 else bool(refused)),
                "SUBMIT_GUARD")
        receipt = value.get("receipt", {})
        require(receipt.get("backend") == "host" and receipt.get("attempts") == []
                and receipt.get("quality_status") == "unassessed", "SUBMIT_RECEIPT")
        require(receipt.get("original_sha256") == "sha256:" + sha256(SOURCE.encode()).hexdigest()
                and receipt.get("text_sha256") == "sha256:" + sha256(expected_text.encode()).hexdigest(),
                "SUBMIT_RECEIPT_HASH")


def _request(rid, method, params):
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}


def _start():
    return [_request(1, "initialize", {"protocolVersion": "2025-06-18",
        "capabilities": {"sampling": {}}, "clientInfo": {"name": "frozen-articulate-check", "version": "1"}}),
        {"jsonrpc": "2.0", "method": "notifications/initialized"}]


def _call(rid, name, arguments):
    return _request(rid, "tools/call", {"name": name, "arguments": arguments})


def _environment(home, closed_url):
    retained = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE"}
    env = {k: v for k, v in os.environ.items() if k.upper() in retained}
    windows = next((v for k, v in env.items() if k.upper() == "SYSTEMROOT"), "C:/Windows")
    env.update({k: str(home) for k in ("FLYWHEEL_HOME", "USERPROFILE", "HOME", "TEMP", "TMP",
                                      "APPDATA", "LOCALAPPDATA")})
    env.update(PATH=str(Path(windows) / "System32"), PYTHONUTF8="1",
               ARTICULATE_MCP_TOOLS="all", ARTICULATE_LOCAL_ONLY="0",
               ARTICULATE_OPENAI_BASE_URL=closed_url, ARTICULATE_OLLAMA_URL=closed_url,
               OPENAI_BASE_URL=closed_url, ANTHROPIC_BASE_URL=closed_url,
               OLLAMA_HOST=closed_url, HTTP_PROXY=closed_url, HTTPS_PROXY=closed_url,
               ALL_PROXY=closed_url, NO_PROXY="")
    return env


def check(executable, version, receipt):
    executable = Path(executable).resolve()
    require(executable.is_file(), "EXECUTABLE_MISSING")
    receipt.update(executable=str(executable), requested_version=version,
                   executable_sha256="sha256:" + sha256(executable.read_bytes()).hexdigest())
    with tempfile.TemporaryDirectory(prefix="frozen-articulate-") as temporary, socket.socket() as closed:
        home = Path(temporary)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            closed.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        closed.bind(("127.0.0.1", 0))  # Reserve a port without listening or serving.
        env = _environment(home, f"http://127.0.0.1:{closed.getsockname()[1]}")
        first = _start() + [_request(2, "tools/list", {}), _call(3, "articulate.doctor", {})]
        for name in ("judge", "fix", "polish"):
            for backend in BACKENDS:
                first.append(_call(len(first), name, {"text": SOURCE, "backend": backend}))
        first += [_call(19, "edit_plan", {"text": SOURCE}),
                  _call(20, "fix", {"text": SOURCE, "backend": "auto"})]

        def run(requests, ids):
            wire = "".join(json.dumps(row) + "\n" for row in requests)
            return parse_replies(run_mcp_process(executable, ARGS, home, env, wire,
                                                timeout=30, max_bytes=2_000_000), ids)

        plan = validate_initial(run(first, set(range(1, 21))), version)
        receipt["observed_version"] = version
        second = _start() + [_call(2, "edit_submit", {"text": SOURCE,
            "rewrite": plan["masked_text"].replace("contains", "has"), "plan_id": plan["plan_id"]}),
            _call(3, "edit_submit", {"text": SOURCE, "rewrite": BAD, "plan_id": plan["plan_id"]})]
        validate_submissions(run(second, {1, 2, 3}), version)
        receipt.update(tool_names=sorted(TOOLS), tool_set="local", local_only=True,
                       backend_refusals=15, numeric_change_refused=True,
                       host_edit_roundtrip=True, sampling_requests=0, sessions=2)
    receipt["isolated_runtime_removed"] = not home.exists()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--expected-version", required=True, help="Expected Articulate version")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = {"schema": "flywheel.frozen-articulate-check/v1", "verdict": "HOLD",
        "requested_version": args.expected_version,
        "acceptance": "Restricted frozen stdio command with synthetic local host edits.",
        "does_not_prove": ["global egress prevention", "installed client compatibility",
                           "installer or clean OS acceptance", "semantic equivalence or factual correctness",
                           "model-backed quality or untested tool workflows"]}
    try:
        check(args.executable, args.expected_version, receipt)
        receipt["verdict"] = "PASS"
    except Exception as exc:
        receipt["failure"] = str(exc) if type(exc) is RuntimeError else type(exc).__name__
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

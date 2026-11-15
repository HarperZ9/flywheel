"""Exercise an installed wheel over stdio; optionally call an installed Ollama model.

Run outside the unit suite: python scripts/smoke_editor.py --python VENV_PYTHON
--output transcript.json [--ollama --model qwen3:8b]. Never downloads a model.
"""
import argparse
import json
import os
import queue
import subprocess
import threading
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--python", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--ollama", action="store_true")
    ap.add_argument("--model", default="qwen3:8b")
    args = ap.parse_args()
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("ARTICULATE_") or name in (
                "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PYTHONPATH"):
            env.pop(name, None)
    env.update(PATH="", PYTHONIOENCODING="utf-8", ARTICULATE_BACKEND="auto",
               ARTICULATE_CLAUDE_CLI="missing-articulate-smoke-cli",
               ARTICULATE_OLLAMA_URL="http://127.0.0.1:1")
    if args.ollama:
        env.update(ARTICULATE_LOCAL_ONLY="1", ARTICULATE_LOCAL_MODEL=args.model,
                   ARTICULATE_OLLAMA_URL="http://127.0.0.1:11434")
    transcript = {"kind": "ollama" if args.ollama else "host", "events": []}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([args.python, "-m", "articulate.local_mcp"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            env=env, cwd=str(output.parent))
    replies = queue.Queue()

    def reader():
        for line in proc.stdout:
            replies.put(json.loads(line))
        replies.put(None)

    threading.Thread(target=reader, daemon=True).start()
    request_id = 0

    def request(method, params):
        nonlocal request_id
        request_id += 1
        msg = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        transcript["events"].append({"request": msg})
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        reply = replies.get(timeout=650)
        transcript["events"].append({"response": reply})
        output.write_text(json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8")
        assert reply and reply.get("id") == request_id, reply
        assert "error" not in reply, reply
        return reply["result"]

    def call(name, arguments):
        result = request("tools/call", {"name": name, "arguments": arguments})
        assert not result.get("isError"), result
        payload = json.loads(result["content"][0]["text"])
        assert payload["ok"], payload
        return payload

    try:
        request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "scripted-host", "version": "1"}})
        listing = request("tools/list", {})
        assert {"edit_plan", "edit_submit"} <= {t["name"] for t in listing["tools"]}
        original = "We really saved 3 files.\n\nRead https://example.com/docs."
        if args.ollama:
            for name in ("fix", "judge", "polish"):
                result = call(name, {"text": "We really saved 3 files.",
                                     "backend": "ollama", **({"passes": 1} if name == "polish" else {})})
                assert result["backend"] == "ollama", result
                assert result["model"] == args.model, result
                assert result["receipt"]["backend"] == "ollama", result
        else:
            offered = call("fix", {"text": original})
            assert offered["backend"] == "host" and offered["plan_id"]
            plan = call("edit_plan", {"text": original})
            good = call("edit_submit", {"text": original,
                        "rewrite": "We saved 3 files.\n\nRead https://example.com/docs.",
                        "plan_id": plan["plan_id"], "model": "scripted-host"})
            assert good["gate_after"] == "ok" and not good["refused"], good
            assert good["receipt"]["backend"] == "host", good
            bad = call("edit_submit", {"text": original,
                       "rewrite": "We saved 4 files.\n\nRead the docs.",
                       "plan_id": plan["plan_id"], "model": "scripted-host"})
            assert bad["text"] == original and len(bad["refused"]) >= 2, bad
        transcript["passed"] = True
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        transcript["server_exit_code"] = proc.returncode
        transcript["stderr"] = proc.stderr.read()
        output.write_text(json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"passed": transcript.get("passed", False), "transcript": str(output)}))


if __name__ == "__main__":
    main()

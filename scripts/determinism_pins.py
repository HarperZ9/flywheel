#!/usr/bin/env python3
"""determinism_pins.py -- pin the determinism surface per rung, then witness it.

`rung_pins.py` answers "what did we preregister"; `verify_rung_digests.py`
answers "does the local store hold it". Neither one asks the question this
module asks: once a rung is SERVED, what did the server actually say about how
it will run it? Runtime build, the sampler tuple, the context window, the
KV-cache type. Those are not weight digests, they are the surface a
nondeterministic serving stack could drift on without the weights changing at
all.

A pin does not create determinism. It localizes blame: if a witness run later
disagrees with a pin, the pin says exactly what changed (runtime version,
sampler, num_ctx, ...), rather than leaving "something is different" as the
only observation. That is the same honest-null discipline `pool.py` uses for
generation fingerprints, applied to the serving surface instead of the
sampling loop.

Every field the server does not expose is recorded as null, never omitted: a
missing key would be indistinguishable from a bug in the code that reads it
back. The rung names are never hand-listed here; they come from the FROZEN
preregistration via `rung_pins.py`, the same no-drift rule `verify_rung_digests.py`
already follows.

Every function that would reach the network takes an injectable `fetch(path,
payload=None)`. The default implementation is the only place `urllib` is used:
GET when no payload is given (`/api/version`), POST of a JSON body otherwise
(`/api/show`). Tests inject a fake and never touch a socket.

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rung_pins import frozen_prereg, parse_pins, pins_in_order  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PINS_PATH = REPO / "artifacts" / "prereg" / "determinism-pins.json"

SCHEMA = "flywheel.determinism-pins/v1"

# The one sampler every rung is captured under. A single tuple, not one per
# rung, because the point of pinning it is to hold it fixed while everything
# else varies.
SAMPLER_TUPLE = {"temperature": 0, "top_k": 1, "top_p": 1.0, "seed": 7,
                 "repeat_penalty": 1.0}

DOES_NOT_PROVE = [
    "NOT_PROVES_OUTPUT_DETERMINISM: these pins fix runtime, sampler, and "
    "context shape as reported by the server. They do not prove the server "
    "reproduces identical output across repeated calls; the repeat-run "
    "digest baseline is what would show that, honestly, including when it "
    "does not hold.",
    "NOT_PROVES_ANCHOR: a captured pin file is not yet an attested event. "
    "Only the possession ceremony (prereg_event.py) turns it into a ledger "
    "entry with a consistency proof.",
    "NOT_PROVES_ABSENT_FIELD_IS_STABLE: a null field (digest, num_ctx, "
    "kv_cache_type) means the server did not expose it at capture time, not "
    "that it cannot change. A witness run cannot diff what was never "
    "observed.",
    "NOT_PROVES_THE_WHOLE_RUNTIME: /api/version and /api/show are two "
    "endpoints. A change in serving behavior that neither endpoint reports "
    "is invisible to this pin file by construction.",
]

DEFAULT_HOST = "127.0.0.1:11434"


def default_base_url() -> str:
    """OLLAMA_HOST, defaulted, never a literal drive path (this is a public
    repo; the operator's environment is the only place a host belongs)."""
    host = os.environ.get("OLLAMA_HOST", "").strip() or DEFAULT_HOST
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"http://{host}".rstrip("/")


def _default_fetch(base_url: str):
    """fetch(path, payload=None) -> dict. GET when payload is None, POST of a
    JSON body otherwise. The only place this module calls urllib."""
    base = base_url.rstrip("/")

    def fetch(path: str, payload: dict | None = None) -> dict:
        url = base + path
        if payload is None:
            request = urllib.request.Request(url)
        else:
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    return fetch


def runtime_record(base_url: str, fetch=None) -> dict:
    fetch = fetch or _default_fetch(base_url)
    doc = fetch("/api/version") or {}
    return {"engine": "ollama", "version": doc.get("version"),
            "host_os": platform.system()}


def _num_ctx_from_parameters(doc: dict) -> int | None:
    """/api/show's "parameters" is a raw multi-line "key value" blob, not
    structured JSON. Absent or unparsable is null, not an exception: a
    server that changed its own output format should not crash the pin."""
    parameters = doc.get("parameters")
    if not isinstance(parameters, str):
        return None
    for line in parameters.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "num_ctx":
            try:
                return int(parts[1])
            except ValueError:
                return None
    return None


def rung_record(base_url: str, model: str, fetch=None) -> dict:
    fetch = fetch or _default_fetch(base_url)
    doc = fetch("/api/show", {"model": model}) or {}
    return {
        "model": model,
        "digest": doc.get("digest"),
        "num_ctx": _num_ctx_from_parameters(doc),
        "kv_cache_type": doc.get("kv_cache_type"),
        "sampler": dict(SAMPLER_TUPLE),
    }


def default_models(repo: Path = REPO) -> list[str]:
    """The nine rung model names, read from the FROZEN preregistration. Never
    a hand-list: a rung renamed in the prereg is a rung renamed here too."""
    text, _ = frozen_prereg(repo)
    pins = parse_pins(text)
    return [pin["model"] for pin in pins_in_order(pins)]


def cites_prereg_sha256(repo: Path = REPO) -> str:
    _, record = frozen_prereg(repo)
    return record["frozen_sha256"]


def capture(base_url: str, models: list[str], fetch=None) -> dict:
    fetch = fetch or _default_fetch(base_url)
    return {
        "schema": SCHEMA,
        "cites_prereg_sha256": cites_prereg_sha256(),
        "runtime": runtime_record(base_url, fetch=fetch),
        "rungs": [rung_record(base_url, model, fetch=fetch) for model in models],
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def canonical_bytes(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_of(doc: dict) -> str:
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


def save(doc: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(doc))


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _diff_fields(label: str, old: dict, new: dict, fields) -> list[str]:
    out = []
    for field in fields:
        pinned, observed = old.get(field), new.get(field)
        if pinned != observed:
            out.append(f"{label}.{field} drift: pinned={pinned!r} "
                       f"observed={observed!r}")
    return out


RUNTIME_FIELDS = ("engine", "version", "host_os")
RUNG_FIELDS = ("digest", "num_ctx", "kv_cache_type", "sampler")


def witness(base_url: str, pins_path: Path, fetch=None) -> list[str]:
    """Re-capture runtime + rungs and diff against the pins on disk. Any
    "baselines" key (Task 2's own mode) is not re-derived and not diffed
    here. Empty list means clean; a non-empty entry names the exact field
    that no longer matches."""
    fetch = fetch or _default_fetch(base_url)
    pinned = load(pins_path)

    drift: list[str] = []
    fresh_runtime = runtime_record(base_url, fetch=fetch)
    drift.extend(_diff_fields("runtime", pinned.get("runtime") or {},
                              fresh_runtime, RUNTIME_FIELDS))

    pinned_rungs = {r.get("model"): r for r in pinned.get("rungs", [])}
    for model in pinned_rungs:
        fresh_rung = rung_record(base_url, model, fetch=fetch)
        drift.extend(_diff_fields(f"rung {model}", pinned_rungs[model],
                                  fresh_rung, RUNG_FIELDS))
    return drift


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", action="store_true",
                       help="capture the determinism surface for the nine "
                            "prereg rungs and write the pins file")
    group.add_argument("--witness", action="store_true",
                       help="re-capture and diff against an existing pins file, "
                            "exit 1 on drift")
    ap.add_argument("--json", dest="as_json", action="store_true")
    ap.add_argument("--base-url", default=None,
                    help="defaults to $OLLAMA_HOST, else 127.0.0.1:11434")
    ap.add_argument("--pins-path", default=str(DEFAULT_PINS_PATH))
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    base_url = args.base_url or default_base_url()
    pins_path = Path(args.pins_path)

    if args.capture:
        models = default_models()
        doc = capture(base_url, models)
        save(doc, pins_path)
        digest = sha256_of(doc)
        if args.as_json:
            print(json.dumps(doc, sort_keys=True, indent=1))
        else:
            print(f"captured {len(doc['rungs'])} rung(s) -> {pins_path}")
            print(f"sha256 {digest}")
        return 0

    try:
        drift = witness(base_url, pins_path)
    except FileNotFoundError as e:
        print(f"pins file not found: {pins_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"pins file is not valid JSON: {pins_path}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps({"pins_path": str(pins_path), "drift": drift,
                          "witnessed": not drift}, indent=1))
    elif drift:
        print("DRIFT DETECTED:")
        for line in drift:
            print(f"  - {line}")
    else:
        print("witnessed clean: runtime and every rung match the pins")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())

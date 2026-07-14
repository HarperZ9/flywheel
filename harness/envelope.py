"""envelope.py — the proof receipt (HARNESS.md §proof-envelope).

Every accepted answer ships this. A third party re-runs `oracle_cmd` on the
candidate and must reproduce `oracle_output_hash` (and thus `verdict`). No
receipt -> no accept. M2 extends this into a per-stage carried chain; M1 ships
the terminal envelope only.
"""
from __future__ import annotations
import base64
import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://flywheel.dev/ProofEnvelope/v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"


@dataclass
class ProofEnvelope:
    task_id: str
    candidate: str
    oracle: str
    oracle_cmd: str
    oracle_output_hash: str
    verdict: str
    model_ref: str
    seed: int
    prompt_hash: str
    budget_spent: dict
    retrieved: list[dict] = field(default_factory=list)
    oracle_stdout_excerpt: str = ""
    harness_version: str = "m1"
    injected_context: dict | None = None
    admission: dict | None = None
    chain: list[dict] = field(default_factory=list)
    # offset-bound citations: each is a byte range of a frozen source,
    # {source_sha256, start_byte, end_byte, quote_sha256}; verified by
    # re-slicing the source (verify_citations below)
    citations: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def _content_preimage(self) -> str:
        d = asdict(self)
        for k in ("oracle_output_hash", "verdict", "oracle_stdout_excerpt"):
            d.pop(k, None)
        return json.dumps(d, sort_keys=True)

    def content_hash(self) -> str:
        """Short display id (16 hex). Not the collision-resistant hash: use
        content_sha256() for signing/interop."""
        return hashlib.sha256(self._content_preimage().encode()).hexdigest()[:16]

    def content_sha256(self) -> str:
        """Full-length, algorithm-tagged content digest (sha256:<64 hex>), in the
        multihash/OMS style. This is the collision-resistant hash real supply-chain
        tooling expects; 64-bit truncation is within reach of a resourced adversary."""
        return "sha256:" + hashlib.sha256(self._content_preimage().encode()).hexdigest()

    def to_in_toto_statement(self) -> dict:
        """This receipt as an in-toto v1 Statement so any in-toto / SLSA-aware
        verifier or SBOM ingester can consume it. The subject digest is the full
        content hash; the predicate is the envelope unchanged."""
        return {
            "_type": IN_TOTO_STATEMENT_TYPE,
            "subject": [{
                "name": self.task_id or "flywheel-answer",
                "digest": {"sha256": self.content_sha256().split(":", 1)[1]},
            }],
            "predicateType": PREDICATE_TYPE,
            "predicate": asdict(self),
        }

    def to_dsse_envelope(self) -> dict:
        """The Statement wrapped in a DSSE envelope (unsigned; signatures=[]). A
        detached signer (cosign sign-blob, openssl dgst -sign) fills signatures
        later without changing this shape, so no signing dependency ships here."""
        payload = json.dumps(self.to_in_toto_statement(), sort_keys=True).encode()
        return {
            "payloadType": DSSE_PAYLOAD_TYPE,
            "payload": base64.b64encode(payload).decode("ascii"),
            "signatures": [],
        }

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def verify_citations(citations: list, resolve) -> dict:
    """Re-check offset-bound citations. `resolve(source_sha256)` returns
    the frozen source bytes or None. Verified means the byte slice hashes
    to the quote; drift means it does not (including out-of-range
    offsets); unverifiable means the source could not be resolved. Only
    all-verified counts as verified overall."""
    verdicts = []
    for c in citations or []:
        src = resolve(str(c.get("source_sha256", "")))
        if src is None:
            verdicts.append({**c, "verdict": "unverifiable",
                             "reason": "source not resolvable"})
            continue
        try:
            start, end = int(c["start_byte"]), int(c["end_byte"])
        except (KeyError, TypeError, ValueError):
            verdicts.append({**c, "verdict": "drift",
                             "reason": "missing or non-integer offsets"})
            continue
        piece = src[start:end]
        ok = (0 <= start < end <= len(src)
              and hashlib.sha256(piece).hexdigest()
              == str(c.get("quote_sha256", "")))
        verdicts.append({**c, "verdict": "verified" if ok else "drift"})
    return {"schema": "flywheel.citations/v1", "verdicts": verdicts,
            "all_verified": bool(verdicts) and all(
                v["verdict"] == "verified" for v in verdicts)}


def load_envelope(path: str | Path) -> ProofEnvelope:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProofEnvelope(**d)


def verdict_from_oracle(passed: bool) -> str:
    return "PASS" if passed else "FAIL"

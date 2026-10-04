"""pysyft_receipt_demo.py -- run a real PySyft job end to end, then emit its receipt.

Needs syft-job built from OpenMined/PySyft at or after commit
36e65162ad2cfbae66d714db8d5c711e19a3a185 (PR #9536), and `cryptography` for the
throwaway signing key. It does not run on Windows today: syft-job's arrival check
compares a newline-normalized hash with the raw on-disk bytes, so a CRLF checkout
never leaves the "received" state. Linux and WSL work.

The flow, all on one machine in a temporary SyftBox folder:
1. The data owner (DO) holds a private item set and a private stand-in model in
   its own private folder. The model is a deliberately imperfect adder, so the
   score is not trivially 100%.
2. The data scientist (DS) submits a Python job that reads both, predicts, and
   writes per-item rows to outputs/results.jsonl.
3. The DO lists the job, approves it with a reason, and runs approved jobs.
   PySyft hashes the job at arrival and approval and runs only a matching copy.
4. `harness.pysyft_adapter.collect` reads the finished job; the receipt is built,
   signed with a fresh key whose private half is never written, and checked with
   the stdlib verifier. The bundle a stranger needs is written to --out.

    python scripts/pysyft_receipt_demo.py --out bundle/ --nonce <challenge>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import job_result_receipt as jr  # noqa: E402
from harness.job_result_verify import verify  # noqa: E402
from harness.pysyft_adapter import collect  # noqa: E402

DO, DS, JOB = "do@example.org", "ds@example.org", "addition.eval"
JOB_CODE = '''\
import json, os
from pathlib import Path

private = Path(os.environ["SYFTBOX_FOLDER"]) / "do@example.org" / "private" / "eval"
items = json.loads((private / "items.json").read_text())
model = json.loads((private / "model.json").read_text())


def predict(a, b):
    bump = model["odd_odd_offset"] if a % 2 == 1 and b % 2 == 1 else 0
    return str(a + b + bump)


os.makedirs("outputs", exist_ok=True)
with open("outputs/results.jsonl", "w") as f:
    for it in items:
        p = predict(it["a"], it["b"])
        row = {"item_id": it["id"], "prediction": p, "correct": p.strip() == it["answer"].strip()}
        f.write(json.dumps(row, sort_keys=True) + "\\n")
print("rows written:", len(items))
'''


def _private_assets(syftbox: Path, n_items: int, seed: int) -> dict:
    rng = random.Random(seed)
    items = []
    for i in range(n_items):
        a, b = rng.randint(10, 99), rng.randint(10, 99)
        items.append({"id": f"q{i:03d}", "a": a, "b": b, "answer": str(a + b)})
    private = syftbox / DO / "private" / "eval"
    private.mkdir(parents=True)
    (private / "items.json").write_text(json.dumps(items, sort_keys=True))
    (private / "model.json").write_text(json.dumps({"odd_odd_offset": 1}))
    return {"items": items,
            "dataset_sha256": hashlib.sha256((private / "items.json").read_bytes()).hexdigest(),
            "model_sha256": hashlib.sha256((private / "model.json").read_bytes()).hexdigest()}


def _run_pysyft(syftbox: Path, work: Path):
    from syft_job.client import JobClient
    from syft_job.config import SyftJobConfig
    from syft_job.job_runner import SyftJobRunner
    code = work / "main.py"
    code.write_text(JOB_CODE)
    ds = SyftJobConfig(syftbox_folder=syftbox, current_user_email=DS)
    JobClient(config=ds).submit_python_job(user=DO, code_path=str(code), job_name=JOB)
    do = SyftJobConfig(syftbox_folder=syftbox, current_user_email=DO)
    job = [j for j in JobClient(config=do).jobs if j.name == JOB][0]
    job.approve(reason="Reads the private eval set, writes per-item rows only.")
    SyftJobRunner(config=do).process_approved_jobs(stream_output=False, timeout=180)
    return JobClient(config=do)


def _sign(body: dict):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from harness.receipt_signer import SigningKey
    key = SigningKey(Ed25519PrivateKey.generate())
    return jr.sign(body, key), key.public_key_bytes.hex()


def _versions() -> dict:
    from importlib.metadata import version
    return {"syft-job": version("syft-job"), "python": platform.python_version(),
            "platform": platform.platform(),
            "pysyft_commit_expected": "36e65162ad2cfbae66d714db8d5c711e19a3a185"}


def _write_bundle(out: Path, paths, envelope, public_hex, assets, report) -> None:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(paths.submission_dir, out / "job", dirs_exist_ok=True)
    shutil.copyfile(paths.results, out / "results.jsonl")
    (out / "receipt.json").write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    (out / "public_key.hex").write_text(public_hex + "\n")
    answers = {it["id"]: it["answer"] for it in assets["items"]}
    (out / "reveal_answers.json").write_text(json.dumps(answers, indent=2, sort_keys=True) + "\n")
    run = {"versions": _versions(), "verify_report": report}
    (out / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--nonce", required=True, help="the requesting party's challenge")
    p.add_argument("--items", type=int, default=50)
    p.add_argument("--seed", type=int, default=20261004)
    a = p.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="pysyft-receipt-") as tmp:
        syftbox = Path(tmp) / "SyftBox"
        syftbox.mkdir()
        assets = _private_assets(syftbox, a.items, a.seed)
        client = _run_pysyft(syftbox, Path(tmp))
        paths, inputs = collect(client, JOB)
        body = jr.build_body(**inputs, nonce=a.nonce,
                             issued_at=datetime.now(timezone.utc).isoformat(),
                             commitments={"dataset_sha256": assets["dataset_sha256"],
                                          "model_sha256": assets["model_sha256"]})
        envelope, public_hex = _sign(body)
        answers = {it["id"]: it["answer"] for it in assets["items"]}
        report = verify(envelope, public_key_hex=public_hex, job_dir=paths.submission_dir,
                        results=inputs["results"], nonce=a.nonce, reviewers=[DO],
                        revealed_answers=answers)
        _write_bundle(Path(a.out), paths, envelope, public_hex, assets, report)
    print(json.dumps({"verdict": report["verdict"], "failed": report["failed"],
                      "score": [body["result"]["correct"], body["result"]["total"]]}))
    return 0 if report["verdict"] == "MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())

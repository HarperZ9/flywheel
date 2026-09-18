"""Train or score the advisory CPU classifier using bounded local JSON files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .classifier_dataset import build_split_manifest, load_examples_jsonl
from .classifier_model import LinearClassifierModel
from .classifier_training import EXAMPLE_KEYS, train_classifier_baseline
from .evidence_json import canonical_bytes, strict_load_json_value


def _load(path: str, limit: int = 16_777_216):
    with Path(path).open("rb") as handle:
        raw = handle.read(limit+1)
    return strict_load_json_value(raw, max_bytes=limit, max_depth=16)


def _write(path: Path, value) -> None:
    with path.open("xb") as handle:
        handle.write(canonical_bytes(value))


def _train(args) -> int:
    loaded = load_examples_jsonl(args.data)
    rows = [{key: row[key] for key in EXAMPLE_KEYS} for row in loaded]
    splits = _load(args.splits)
    manifest = build_split_manifest(rows, splits)
    training = [row for row in rows if splits[row["source_group"]] == "train"]
    if not training:
        raise ValueError("no training examples in the train split")
    out = Path(args.out)
    if out.exists():
        raise ValueError("output directory already exists")
    result = train_classifier_baseline(training, seed=args.seed, epochs=args.epochs,
                                       feature_buckets=args.feature_buckets)
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "model.json", result.model.to_json_dict())
    _write(out / "training-report.json", result.report)
    _write(out / "split-manifest.json", manifest)
    print(json.dumps({"model_ref": result.model.model_ref(),
                      "training_examples": len(training),
                      "split_manifest_sha256": manifest["manifest_sha256"],
                      "automatic_selection_enabled": False}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--data", required=True)
    train.add_argument("--splits", required=True)
    train.add_argument("--out", required=True)
    train.add_argument("--seed", type=int, default=1729)
    train.add_argument("--epochs", type=int, default=30)
    train.add_argument("--feature-buckets", type=int, default=512)
    score = commands.add_parser("score")
    score.add_argument("--model", required=True)
    score.add_argument("--family", required=True)
    score.add_argument("--requests", required=True)
    score.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "train":
        return _train(args)
    model = LinearClassifierModel.load_json(args.model)
    results = model.predict_batch(_load(args.requests), task_family=args.family)
    _write(Path(args.out), results)
    print(json.dumps({"model_ref": model.model_ref(), "requests": len(results),
                      "automatic_selection_enabled": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

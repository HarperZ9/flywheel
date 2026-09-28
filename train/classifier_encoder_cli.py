"""CLI for optional neural classifier encoder training and scoring."""
from __future__ import annotations

import argparse
from pathlib import Path

from harness.classifier_dataset import MANIFEST_SCHEMA, load_examples_jsonl
from harness.evidence_json import canonical_bytes, canonical_sha256, strict_load_json

from .classifier_encoder import (
    EncoderTrainConfig,
    load_local_pretrained,
    train_encoder_classifier,
)
from .classifier_encoder_artifact import load_encoder_artifact, save_encoder_artifact
from .classifier_encoder_runtime import EncoderClassifierRuntime


def _read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(Path(path).read_bytes().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(strict_load_json(line, max_bytes=131_072, max_depth=12))
        except (ValueError, RecursionError) as exc:
            raise SystemExit(f"invalid JSON request at line {line_no}") from exc
    return rows


def _read_bounded(path: str | Path, limit: int) -> bytes:
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(limit + 1)
    except OSError as exc:
        raise SystemExit(f"unreadable JSON file: {path}") from exc
    if len(raw) > limit:
        raise SystemExit(f"JSON file exceeds byte limit: {path}")
    return raw


def _write_json(path: str | Path | None, value: dict | list[dict]) -> None:
    raw = canonical_bytes(value)
    if path is None:
        print(raw.decode("utf-8", "strict"))
    else:
        Path(path).write_bytes(raw)


def _raw_example(row: dict) -> dict:
    return {
        "task_family": row["task_family"],
        "source_group": row["source_group"],
        "request": row["request"],
        "acceptable_choice_ids": row["acceptable_choice_ids"],
        "label_provenance": row["label_provenance"],
    }


def _load_split_manifest(path: str | Path, rows: list[dict]) -> dict:
    try:
        manifest = strict_load_json(
            _read_bounded(path, 16_777_216), max_bytes=16_777_216, max_depth=12)
    except (ValueError, RecursionError) as exc:
        raise SystemExit("invalid split manifest JSON") from exc
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("manifest_sha256") != canonical_sha256(body):
        raise SystemExit("invalid split manifest checksum")
    manifest_hashes = [item.get("example_sha256") for item in manifest.get("examples", [])]
    row_hashes = [row["example_sha256"] for row in rows]
    if sorted(manifest_hashes) != sorted(row_hashes) or len(set(manifest_hashes)) != len(manifest_hashes):
        raise SystemExit("split manifest examples do not match examples file")
    by_hash = {row["example_sha256"]: row for row in rows}
    for item in manifest["examples"]:
        row = by_hash[item["example_sha256"]]
        if item.get("source_group") != row["source_group"] or item.get("task_family") != row["task_family"]:
            raise SystemExit("split manifest row does not match examples file")
        if item.get("acceptable_choice_ids") != row["acceptable_choice_ids"]:
            raise SystemExit("split manifest labels do not match examples file")
    return manifest


def _load_training_examples(path: str | Path, split_manifest: str | Path | None = None) -> list[dict]:
    rows = load_examples_jsonl(path)
    if split_manifest is not None:
        manifest = _load_split_manifest(split_manifest, rows)
        train_hashes = {
            item["example_sha256"]
            for item in manifest["examples"]
            if item.get("split") == "train"
        }
        rows = [row for row in rows if row["example_sha256"] in train_hashes]
        if not rows:
            raise SystemExit("split manifest selected no train examples")
    return [_raw_example(row) for row in rows]


def _train(args) -> int:
    tokenizer, encoder = load_local_pretrained(
        args.pretrained_model, device=args.device,
        attn_implementation=args.attn_implementation)
    examples = _load_training_examples(args.examples, args.split_manifest)
    config = EncoderTrainConfig(
        seed=args.seed,
        epochs=args.epochs,
        learning_rate=args.encoder_lr,
        head_learning_rate=args.head_lr,
        batch_size=args.batch_size,
        max_steps=args.max_steps,
        max_length=args.max_length,
        device=args.device,
        fine_tune_last_n_layers=args.fine_tune_last_n_layers,
        progress_every=args.progress_every,
    )

    def progress(row: dict) -> None:
        print(f"[classifier-encoder] step={row['step']} loss={row['loss']:.6f} "
              f"examples={row['examples_processed']}")

    result = train_encoder_classifier(
        examples,
        tokenizer=tokenizer,
        encoder=encoder,
        config=config,
        progress_callback=progress if args.progress_every else None,
    )
    manifest = save_encoder_artifact(
        args.out, result, pretrained_model_path=args.pretrained_model)
    _write_json(Path(args.out) / "train_manifest_echo.json", manifest)
    return 0


def _score(args) -> int:
    loaded = load_encoder_artifact(args.artifact, device=args.device)
    runtime = EncoderClassifierRuntime(
        loaded.model,
        loaded.tokenizer,
        loaded.report["artifact_identity"],
        cache_size=args.cache_size,
        encode_batch_size=args.encode_batch_size,
        device=args.device,
    )
    envelopes = runtime.score_batch(
        _read_jsonl(args.requests), task_family=args.task_family)
    _write_json(args.out, envelopes)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="classifier_encoder_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    train = sub.add_parser("train")
    train.add_argument("--examples", required=True)
    train.add_argument("--split-manifest", default=None,
                       help="optional flywheel.classifier-split-manifest/v1; "
                            "must cover all examples, only split=train rows train")
    train.add_argument("--pretrained-model", required=True)
    train.add_argument("--out", required=True)
    train.add_argument("--device", default="cpu")
    train.add_argument("--attn-implementation", choices=["sdpa", "eager"], default="sdpa")
    train.add_argument("--seed", type=int, default=0)
    train.add_argument("--epochs", type=int, default=3)
    train.add_argument("--encoder-lr", type=float, default=2e-5)
    train.add_argument("--head-lr", type=float, default=1e-3)
    train.add_argument("--batch-size", type=int, default=4)
    train.add_argument("--max-steps", type=int, default=None)
    train.add_argument("--max-length", type=int, default=256)
    train.add_argument("--fine-tune-last-n-layers", type=int, default=0)
    train.add_argument("--progress-every", type=int, default=10)
    train.set_defaults(func=_train)
    score = sub.add_parser("score")
    score.add_argument("--artifact", required=True)
    score.add_argument("--requests", required=True)
    score.add_argument("--task-family", required=True)
    score.add_argument("--out", default=None)
    score.add_argument("--device", default="cpu")
    score.add_argument("--cache-size", type=int, default=4096)
    score.add_argument("--encode-batch-size", type=int, default=32)
    score.set_defaults(func=_score)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

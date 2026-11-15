# Model-Eval Proof Packet (`proof_surface.model_eval`)

> A model run + eval set + objective -> a **default-deny** promotion receipt.

Wedge #4 (model-foundry / eval forge).

## One command

```bash
python -m proof_surface model-eval \
  --input examples/model_eval/eval.json \
  --claim "the model met its objectives on the eval suite" \
  --scope "one offline eval suite; default-deny promotion" \
  --packet-id demo-model-eval --out demo-out
# emits: packet.json · report.md · crucible-thesis.json · crucible-measurements.json
```

The input JSON carries `model` (id/provider/config_hash), `eval_set`
(name/ref/sha256/size), `objective`, and `metrics`. Each metric declares a
`direction` — `maximize` (deviation = how far below target), `minimize` (how far
above), or `within` (absolute distance) — with a `target` and `tolerance`. The
verdict uses the shared crucible-faithful rule and re-derives through real
crucible.

## Default-deny promotion

The promotion `decision` is derived from the overall verdict, and the validator
enforces it: **a model is promoted only if the overall verdict is MATCH**
(`DRIFT` -> reject, `UNVERIFIABLE` -> needs-human). A packet that claims `promote`
without an overall MATCH does not validate. Zero-dependency; inherits the
family's forbidden-field and authority-language guards.

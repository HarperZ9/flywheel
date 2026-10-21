# Eval receipts name the runtime and the access

An eval receipt says which model ran over which dataset and what the oracle
decided. Two more facts bound what a reader can take from it. The first is the
runtime that produced the results. The second is what the evaluator could see.
Both are sealed into every receipt `flywheel.eval-receipt/v1` writes, and
neither is guessed: a field nobody declared reads `unknown`.

## Runtime identity

The same weights and the same prompt do not fix the computation. In the
`watching` experiments (github.com/SauersML/watching), compiled activation
capture changed 86 to 90 percent of next-token logits in Hugging Face, eager
capture changed none, and a detector trained on one GPU reversed its signal on
another. Batch shape, dtype and the serving framework change the floating-point
path as well.

`harness.runtime_identity` records ten fields:

| Field | Example |
|---|---|
| `serving_framework`, `serving_version` | `vllm`, `0.11.2` |
| `gpu_model` | `L40S` |
| `dtype` | `bf16` |
| `compile_mode` | `eager`, `torch.compile` |
| `batch_shape` | `1`, `64` |
| `batch_invariant`, `deterministic` | `true`, `false`, `unknown` |
| `capture_hooks` | `none`, or a sorted list such as `layer14.q_norm` |
| `kernel_stack` | `torch 2.10.0+cu128` |

The same block is part of the harness-config hash of a code session. Set
`session.runtime`, or give a backend a `runtime` dict, and changing any one of
the ten fields changes the hash. Unknown keys are refused, so a misspelled field
cannot hide as `unknown`.

```python
from harness.runtime_identity import rerun_witness_receipts
rerun_witness_receipts(receipt_a, receipt_b)["verdict"]  # MATCH, DRIFT or UNVERIFIABLE
```

The rerun witness returns MATCH when the result rows agree. A mismatch is DRIFT
only when both runs declared deterministic, batch-invariant execution and every
field is known and equal. Any other mismatch is UNVERIFIABLE, and `fields`
names the runtime fields that differ or are unknown.

## Access statement

`harness.eval_access` records six surfaces, each `granted`, `not_granted` or
`unknown`: `api_outputs`, `logits`, `activations`, `weights`, `checkpoints` and
`internal_tools`. The block also carries the redacted categories and who
redacted them. A run through `POST /api/eval/run` goes through a provider endpoint,
so it records API outputs as granted and the other five as not granted.

A verifier call can name the scope of the claim it is checking:

```python
verify_eval_receipt(receipt, claim_scope="training_time")
```

| Scope | Needs |
|---|---|
| `output_behavior` | `api_outputs` |
| `output_distribution` | `api_outputs`, `logits` |
| `internal_state` | `activations` |
| `weight_level` | `weights` |
| `training_time` | `checkpoints` |
| `deployment_tooling` | `internal_tools` |

When a needed surface is not recorded as granted, the verdict is UNVERIFIABLE
with `failure_class` `ACCESS_SHORT_OF_CLAIM`, and the detail names the missing
surfaces. `POST /api/eval/verify` takes the same `claim_scope` field. A receipt sealed
before these blocks existed still verifies, and it backs no scoped claim.

## Measured

- Each of the 10 runtime fields changes the config hash and the receipt seal
  when flipped alone, 10 of 10 (`tests/test_runtime_identity.py`).
- Each of the 10 fields, changed between two runs with different outputs, gives
  UNVERIFIABLE and names that field. A naive witness that calls every output
  mismatch DRIFT fails the compile-mode case; this one does not.
- Each of the 6 claim scopes is refused when its surface is not granted or
  unknown, and passes when it is granted. Changing one surface changes the seal,
  and editing the block after sealing is TAMPERED (`tests/test_eval_access.py`).

## Does not prove

Both blocks are declarations sealed with the result. Flywheel does not probe the
GPU or the serving stack, and equal runtime fields do not prove equal kernels.
An access grant does not show the evaluator used it, and a recorded redaction
does not show the redaction was justified.

# Cost receipts: time taken against the hardware floor

A model call takes some number of seconds. That number alone says little about
waste. Cost receipts set it beside the fastest time the hardware could ever
manage, so a reader can see how far a run sits from that limit.

## How the floor is computed

A generation call does two kinds of work:

- Prefill runs every prompt token through the weights.
- Decode reads all the weights once per step to make one new token.

Each phase can go no faster than the slower of two limits: arithmetic at the
chip's peak rate, and reading the weights at the memory's peak bandwidth. The
floor is the sum of the two phases. No kernel on that chip can beat it.

`harness/cost_floor.py` holds the formula and the hardware table. Each rate
names its source:

| Hardware | Memory bandwidth | Arithmetic rate | Source |
|:--|:--|:--|:--|
| RTX 4090 | 1008 GB/s | 330.3 TFLOPS, dense FP16 tensor | NVIDIA Ada GPU Architecture whitepaper v2.02, Appendix A |

You can pass your own `Hardware(...)` for another chip.

```python
from harness.cost_floor import ModelProfile, receipt
r = receipt(measured_s=1.334, prompt_tokens=61, completion_tokens=85,
            model=ModelProfile(params=14_770_033_664, weight_bytes=8_988_111_146),
            hardware="rtx-4090")
r["floor_s"], r["ratio"]   # 0.767, 1.74
```

Each receipt (`flywheel.cost-floor/v1`) carries:

- measured time, the floor and their ratio
- each phase's floor, and whether memory or arithmetic bounds it
- the token counts and batch size
- the model's size
- the hardware rates and their source
- the assumptions and a `does_not_prove` line

## In search

Set `hardware` and `model_profile` on the search arm. The search stage then
carries one receipt per candidate, plus a summary with total and median
ratios:

```python
from harness.eval import ArmConfig
arm = ArmConfig(name="search", n_candidates=4, hardware="rtx-4090",
                model_profile={"params": 14_770_033_664, "weight_bytes": 8_988_111_146})
```

A candidate with no timing or no provider token counts is counted as untimed.
The receipt never guesses its tokens. Without `hardware`, search writes no cost
section.

## Measured on a real run

Every generation call in the search effort-gate confirmation run got a
receipt: 600 calls from a local 14B coder model (Q4_K_M) on one RTX 4090, the
bar set before the floor was computed.

| Set | Calls | Measured | Floor | Ratio, total | Ratio, median [p10, p90] | Below floor |
|:--|:--|:--|:--|:--|:--|:--|
| hard_v2 | 550 | 1482 s | 1092 s | 1.36 | 1.33 [1.30, 1.50] | 0 |
| hard | 50 | 87 s | 39 s | 2.25 | 1.32 [1.30, 1.61] | 0 |

- No call ran faster than its floor, so the floor held as a lower bound on
  this run.
- Decode is 99% of the floor, and decode is bound by memory bandwidth.
- The typical call sits about a third above the limit.
- The hard set's total is inflated by its first call, which waited 35 seconds
  for the model to load.

As an outside check, the server's own log reported decode at 78.5 tokens per
second. The bandwidth limit for this weight file is about 112, which puts
decode alone at about 1.43 times the floor. That agrees with the receipts.

The full summaries are in `project-docs/records/cost-floor/`.

## Limits

- Measured time is wall time around one HTTP request, so it includes the
  server's and the client's own overhead.
- The floor ignores KV-cache reads and activations, so it is optimistic for
  long contexts.
- The rates are peak figures that assume full use of the chip.
- A ratio says how much time was lost. It does not say where the time went.

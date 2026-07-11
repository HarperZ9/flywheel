# Flywheel: Product Copy

Ready-to-place copy in the product voice. Take these verbatim or trim them. Two
rules: do not add a claim the receipts do not support (see BENCHMARKS.md), and
keep the honest null where it is. It is what makes the strong claims believable.

**Live source of truth:** the public repository is
**https://github.com/HarperZ9/flywheel**. Its README is the canonical short pitch;
this file expands it for the site.

---

## Name and one-liner

**Flywheel**: the router and harness that verifies.

Alternate one-liners (pick per placement):
- Route to any model. Verify every answer. Keep the receipt.
- Does what every router does, plus the one thing none of them do.
- Bring your keys, or bring your weights.

## Hero

**Headline:** A companion for every model.

**Subhead:** Route to any model, local or hosted, online or offline. Flywheel
answers what it can verify, escalates only the hard part, and hands you a receipt
you can re-run yourself. It does what every router and runner does, plus the one
thing none of them do: it checks the work.

**Primary call to action:** Watch the harness run
**Secondary call to action:** See every tool

## The one-line promise (use as a pull quote)

Every number on every page is a fetch of a receipt file you can re-check offline.

## Why Flywheel (the wedge)

Routers route. Local runners run. Agent harnesses orchestrate. Not one of them
checks whether the answer is right and hands you proof. Flywheel does all of their
jobs on one surface, and adds the verify layer none of them have. The authority
that accepts an answer is an external check, never a model grading its own work.

Four supporting blurbs:

- **Every provider, one surface.** Local weights, a local server, or any hosted
  provider you hold a key for. One roster, one verified path behind all of them,
  credentials shown as presence only, never a value.
- **A record you can keep.** Every accepted answer carries a receipt: the inputs,
  the check that passed, and hashes anyone can re-run offline. This is the layer no
  other router has.
- **Answer local, escalate the hard part.** Flywheel answers what it can verify
  locally for near-zero cost, and routes only the genuinely hard slice to a
  stronger tier, on evidence, not a guess.
- **Yours when the network is not.** Bring your keys and it routes online. Bring
  your weights and a capable coder in a single file just under 9 GB runs offline,
  on a plane, when the network is down.

## How it compares (build this as a comparison table)

| | Ordinary router | Local runner | Agent harness | Flywheel |
|---|---|---|---|---|
| Routes to many providers | Yes | No | Some | Yes |
| Runs a local model | No | Yes | Some | Yes |
| Works offline | No | Yes | No | Yes |
| Accepts on an external check | No | No | No | Yes |
| Re-checkable receipt per answer | No | No | No | Yes |
| Answers local, escalates the hard part | No | No | No | Yes |
| One root-hashed shared state | No | No | No | Yes |
| Zero dependencies, one file to run | Varies | Varies | No | Yes |

## Feature blurbs (for a features grid)

- **The universal router.** Every provider in one roster, local weights to hosted
  APIs, with one verified path behind them all. Route to any of them and get a
  receipt with the answer.
- **The companion seat.** Answers locally when it can verify the result, and
  escalates only the hard slice. The stronger tier is named, never called for you.
- **The studio.** Turn a plain goal into a structured prompt whose success a
  machine can check. Confidence is grounded in what an outside check can confirm.
- **The projected world.** One document you and the model both read, sealed under
  a root hash. Change one byte and the hash moves.
- **Receipts everywhere.** Content-addressed and re-checkable. Tamper with one and
  the check fails, which is what makes a pass mean something.

## Run-it-now (show the commands, they are short)

```
python scripts/run_harness_cli.py app --port 8799
```

Then open the surface in a browser. Zero dependencies. Route online with your
keys, or run fully offline against local weights.

## The vision (a manifesto block, present it in full)

Flywheel is the front surface of a verified-inference flywheel: propose with a
cheap local model, dispose with an external check, keep the re-checkable receipt,
and let what passes accumulate. The model is the replaceable half; the
verification harness is the durable half. The same discipline, an external check
that can fail plus a receipt anyone can re-run, scales from routing a single call
to composing a whole spine of accountable tools. This is the largest of those
tools, and the front door to all of them.

## Honest status (keep this, do not soften it)

Flywheel's advantages are in the product, and they are real: it routes to more
places, verifies where nothing else does, runs offline, and reproduces every
receipt. On the separate question of whether verified inference makes the model
itself measurably smarter, it does not overclaim: the measured lift is within
noise today, and it says so. A tool that refuses to overclaim is a tool whose
other claims you can trust.

## Footer line

Flywheel is a companion layer for local and hosted models. The model is the
replaceable half; the verification harness is the durable half.

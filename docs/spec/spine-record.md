# Spine record v1

Every tool in the family writes its own receipt, with its own verdict words and its own chain. A reader who wants to check gather, crucible and emet together needs three parsers and three vocabularies. The spine record is one shape that wraps any tool's receipt, says what it decided in shared words, links into one chain and carries optional cause-and-effect fields. One verifier rechecks it offline. The identifier is `flywheel.spine-record/1`, schema version 1.

Reference code: `harness/spine` (standard library only). Verifier:

```
python -m harness.spine verify RECORD_OR_CHAIN.json
```

Exit 0 is PASS, 1 FAIL, 2 UNVERIFIABLE, 3 UNDECIDED, 64 usage. The verifier hashes, compares and subtracts. It calls no model, network or clock. It is on the entry-point list of `scripts/check_verifier_stdlib.py`, so the C2 import-closure check covers it.

## The verdict vocabulary

The spine uses Flywheel's four verdicts from `harness/verdict.py`. No fifth set was added.

| Spine | Meaning |
|---|---|
| PASS | the check ran and decided in favour |
| FAIL | the check ran and decided against |
| UNDECIDED | the check ran and declined to dispose |
| UNVERIFIABLE | the check could not run, or does not apply |

The four vocabularies in use map onto it like this (`harness/spine/vocab.py`):

| Vocabulary | Used by | Term | Spine |
|---|---|---|---|
| `flywheel` | Flywheel harness | PASS, FAIL, UNDECIDED, UNVERIFIABLE | the same term |
| `integrity` | emet, crucible claims, index, gather corpus, telos proof, proof-surface, mneme drift, Flywheel replay and chain checks | MATCH | PASS |
| | | DRIFT | FAIL |
| | | UNVERIFIABLE | UNVERIFIABLE |
| | emet receipt lattice | RECEIPT_VALID, RECEIPT_TAMPERED, RECEIPT_UNVERIFIABLE | PASS, FAIL, UNVERIFIABLE |
| `organ-bundle` | gather, crucible, index, forum, learn and Flywheel interop entries | pass | PASS |
| | | fail | FAIL |
| | | warn | UNDECIDED |
| | | needs-human | UNDECIDED |
| | | unverified | UNVERIFIABLE |
| | | not-applicable | UNVERIFIABLE |
| | | unknown | UNVERIFIABLE |
| `gate` | accountable-surface, coherence-membrane write gate | allow | PASS |
| | | deny | FAIL |
| | | needs-human | UNDECIDED |

The map loses detail: `warn` and `needs-human` both become UNDECIDED, and `not-applicable` and `unknown` both become UNVERIFIABLE. So a record keeps its source term beside the spine verdict, and the verifier checks that the pair agrees with the table. A consumer branches on the spine verdict. A person reads the source term to learn why. An unknown vocabulary or term raises an error; the code never guesses.

When several checks fold into one verdict, FAIL outranks UNVERIFIABLE, which outranks UNDECIDED, which outranks PASS. A confirmed difference outranks an inability to check, as in emet's SPEC section 5. An empty fold is UNVERIFIABLE.

## The record

| Field | Value |
|---|---|
| `schema` | `"flywheel.spine-record/1"` |
| `schema_version` | `1` |
| `canonical_form` | `"canonical-record/1"` |
| `tool` | the producing tool, such as `"emet"` |
| `source_schema` | the payload's own schema id, such as `"emet-witness-receipt/v1"` |
| `source_vocabulary` | one of the four vocabularies above |
| `source_verdict` | the payload's verdict term in that vocabulary |
| `verdict` | the spine verdict; it must equal the mapped source term |
| `scope` | what the verdict covers, in positive words |
| `payload_sha256` | canonical-record/1 sha256 of the payload |
| `payload` | the tool's own receipt, embedded (optional, needed to recheck) |
| `cause` | cause-and-effect fields (optional, below) |
| `prev_sha256` | `record_sha256` of the record before, `""` for the first |
| `record_sha256` | sha256 over every other field |

Hashes use canonical-record/1 (`docs/spec/canonical-record.md`), because effect and interval fields are floats and that form is the one other languages reproduce. The chain walk is `harness/hash_chain.py`, the walk the scheduler, scan, runner-pool and browser records already share. It gained a `digest` parameter for this; its default is unchanged, so those chains seal byte for byte as before. `make_record` derives the spine verdict from the source term, so a writer cannot state a mismatched pair. `from_native` derives the source term from the payload by the tool's own rule.

## Cause-and-effect fields

All optional. A record without `cause` verifies as before. A record that claims an effect must carry what the claim rests on.

```json
"cause": {
  "intervention": {"field": "temperature", "value": 0.7, "twin_value": 0.0},
  "run":   {"inputs": {"model": "m-1", "seed": 7, "temperature": 0.7}, "outcome": 0.82},
  "twin_digest": "<canonical-record/1 sha256 of twin>",
  "twin":  {"inputs": {"model": "m-1", "seed": 7, "temperature": 0.0}, "outcome": 0.70},
  "effect": 0.12,
  "interval": {"low": 0.05, "high": 0.19, "level": 0.95, "method": "seed bootstrap"},
  "placebo": {"change": {"field": "agent_name", "value": "renamed"},
              "run": {"inputs": {"...": "twin inputs plus agent_name"}, "outcome": 0.71},
              "effect": 0.01,
              "interval": {"low": -0.03, "high": 0.05, "level": 0.95}}
}
```

- **intervention**: the one field that was changed, as declared, with the value in the run and in the twin.
- **twin_digest** and **twin**: the matched run, by digest and embedded.
- **effect**: run outcome minus twin outcome.
- **interval**: bounds on the effect, with its level and method.
- **placebo**: a null-change run. It equals the twin, or differs only by one declared inert change such as a renamed agent.

What the verifier checks (`harness/spine/cause.py`):

| Case | Result |
|---|---|
| effect with no twin digest | UNVERIFIABLE |
| twin digest with no embedded twin | UNVERIFIABLE |
| embedded twin does not match its digest | FAIL |
| run and twin differ in any field besides the declared one, or not in it | FAIL, naming the fields |
| declared values differ from the values the runs used | FAIL |
| effect is not run outcome minus twin outcome | FAIL |
| interval malformed, or does not hold its effect | FAIL |
| placebo changes a field besides its declared inert change | FAIL |
| placebo effect is not placebo outcome minus twin outcome | FAIL |
| placebo interval holds its effect and excludes zero | UNVERIFIABLE, marked CONFOUNDED |
| placebo with no interval and a nonzero effect | UNDECIDED |

Fields compare by canonical bytes, so `1` and `1.0` are the same value. Effects compare with a relative tolerance of 1e-9.

The verifier takes the outcomes and the interval bounds as given. Recomputing an interval needs the resamples, which a receipt does not carry. That recomputation belongs in crucible's effect claims, the next upgrade in the anatomy.

## Rechecking a tool's own receipt

When the payload is embedded, the verifier checks `payload_sha256`, then rechecks the payload by its tool's published recipe. No tool is imported.

| Source schema | Recipe | Source verdict |
|---|---|---|
| `emet-witness-receipt/v1` | emet SPEC section 17.2: `receipt_id` is sha256 of `json.dumps(body, sort_keys=True, ensure_ascii=True)` with `receipt_id`, `signature` and `witness` left out | DRIFT if any subject drifted, MATCH if all matched, else UNVERIFIABLE |
| `crucible.assessment/1` | crucible `assess.py`: verdict seal, measurement seal and record seal; counts match the rows; each MATCH or DRIFT row follows from its deviation and tolerance | crucible `interop.py` status: pass, fail, unverified, warn, unknown |
| `gather.digest/1` | gather `digest.py`: seal over the sorted receipt projections, availability and storage folded in when set | MATCH when the seal re-derives |

A signed emet receipt is UNVERIFIABLE here, because this verifier holds no key (emet SPEC section 17.3). A crucible recheck without the thesis cannot apply the sealed-tolerance rule or the falsification rule; it checks what the assessment itself carries. A schema with no native checker yet keeps its seal, vocabulary and payload-digest checks and reads UNVERIFIABLE overall.

The recheck verdict is separate from the record's verdict. An emet receipt that honestly records DRIFT rechecks as PASS: the receipt is intact and its verdict follows from what it carries.

## Fixtures

`tests/fixtures/spine` holds five receipts emitted by each tool's own code: two emet witness receipts (MATCH and DRIFT), two crucible assessments (warn and fail) and one gather digest. `SOURCE.txt` there names the commit each came from. The spine's recipes were written from the published formats, and the tests check that they agree with these bytes. Live emission from the lanes into spine form is not wired yet.

## Adopting the spine

A tool adopts the spine by emitting `flywheel.spine-record/1` records, or by letting Flywheel wrap its receipt with `from_native`. Old receipts keep their own formats and verify under their own rules. A record with a `schema_version` newer than the verifier knows reads as UNVERIFIABLE by name.

## Verified

- Each of the five fixtures re-expresses in spine form and rechecks as PASS: `tests/test_spine_verify.py`.
- A twin that differs in two fields and an effect that does not match its twin are refused: `tests/test_spine_cause.py`.
- Existing `hash_chain` seals are unchanged, and records with no cause block verify: `tests/test_spine_compat.py`, `tests/test_hash_chain.py`.
- The spine import closure reaches no third-party package or model runtime: `tests/test_spine_c2.py`, `scripts/check_verifier_stdlib.py`.

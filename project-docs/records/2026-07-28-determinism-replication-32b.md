# Record: 52 of 52 candidates reproduced byte for byte across a full serving restart

**Discharges:** the open clause in the runner-oversubscription addendum, sha256
`2cc37ebf569680f6187753d1454b45a58e622bdda91d595f92a2157ed096e42f`, section 4:
"the regenerated candidates are expected to be byte-identical to the quarantined
ones. That expectation is checkable later against the quarantined copies, and it
has not been checked yet." It has now been checked.

**Register:** the `flavored` profile. Calibrated uncertainty is kept.

---

## 1. What was compared

The `zarankiewicz` pair on rung `telos-coder-32b` was generated twice.

The first attempt was interrupted and had produced 52 unique candidate files
before it died. Those files were moved out of the pool before the restart, so
the pair regenerated into an empty directory with no knowledge of them. The
second attempt ran to completion: 60 tasks, 240 slots, 240 filled, no gaps,
101 unique candidate files, exit 0 after 17422.8 seconds.

Between the two attempts the serving surface was fully restarted. The first
attempt's model runner was orphaned and later killed, the model was unloaded,
the device was returned to 1.7 GB used, and a fresh runner loaded the model
again for the second attempt.

## 2. The result

| quantity | value |
|---|---|
| candidates from the interrupted attempt | 52 |
| unique candidates in the completed pair | 101 |
| candidates from the first attempt NOT reproduced | **0** |
| byte comparison on a sample of eight | identical |

Every candidate the first attempt produced was produced again. The store is
content-addressed, so a matching filename already implies matching bytes; the
sample comparison checks that the addressing itself is sound rather than
assuming it.

## 3. Why it is worth recording

The pinned serving surface claims a fixed model digest, engine version,
quantization, context length, seed list and temperature ladder. This is the
first evidence in this repository that those pins actually buy reproducibility
of the generated text, across a process kill, a session teardown, and a complete
unload and reload of the model.

It also settles the cost question the quarantine raised. Discarding those 52
candidates cost regeneration time and nothing else, which is what the addendum
predicted and had not yet demonstrated.

## 4. Does not prove

- **NOT_PROVES_GENERAL_DETERMINISM.** One family, one rung, one machine, one
  engine version. Nothing here speaks to the other eight rungs, to the crossing
  family, or to any other host.
- **NOT_PROVES_HARDWARE_INVARIANCE.** Both attempts ran on the same device with
  the same driver. A different device, a different offload split, or a different
  engine build are all untested, and the first attempt's processor split was not
  recorded, so this does not even establish that the two runs shared one.
- **NOT_PROVES_THE_PINS_ARE_SUFFICIENT.** Reproducibility held here. That is
  consistent with the pins being sufficient and also consistent with the
  untested factors happening to be constant.
- **NOT_PROVES_ANYTHING_ABOUT_QUALITY.** No candidate was read, scored, or put
  through an accept path to produce this record. It compares bytes and counts
  files, which is all it claims to do.

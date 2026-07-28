# Published-surface leak burn-down (frozen 2026-07-28)

`check_public_instructions.py` held its rule over three instruction filenames
and nothing else. Widening it to the pages a stranger reads first, model cards,
release READMEs, usage and walkthrough docs, surfaced leaks nobody had scanned
for.

The gate went on immediately rather than waiting for the rewrites, using the
mechanism `check_file_gate.py` already uses for the 300-line rule: these counts
are frozen, a NEW leaking surface fails, a grandfathered surface that GAINS a
leak fails, and the list may only shrink. A surface that reaches zero leaves it
and cannot come back.

Written because a 32B model card carrying a build-machine path reached a branch
and was caught by hand. A gate that reads three filenames cannot see the page a
reader opens first.

Internal register docs under `project-docs/records`, `plans` and `specs` are
exempt by design: the canon permits local paths there and forbids them on a
published surface.

Entries for this repository are keyed repo-relative so they match from any
checkout. Entries under `public/` belong to other repositories, are listed
because the gate scans every public repo at the workspace root, burn down in
their own repos, and are simply absent from a fresh clone.

Total at freeze: 31 leak(s) across 11 surface(s).

Burned down since: `project-docs/releases/32B/MODEL_CARD.md` reached zero
on 2026-07-28 and has left the list.

- `project-docs/releases/14B/MODEL_CARD.md` - 4
- `project-docs/releases/14B/README.md` - 2
- `project-docs/releases/14B/RELEASE-CHECKLIST.md` - 2
- `project-docs/releases/14B/SAFETY-ACCOUNTABILITY.md` - 1
- `project-docs/releases/14B/USAGE.md` - 3
- `project-docs/releases/14B/WALKTHROUGH.md` - 11
- `public/accountable-surface/README.md` - 1
- `public/index/README.md` - 1
- `public/public-surface-sweeper/README.md` - 3
- `public/telos-plugin/README.md` - 2

"""Exit codes of BootLoops' `receipt.py verify` on single-mutation inputs from the fuzzer.

    python scripts/cli_probe.py BOOTLOOPS_ROOT OUT_DIR

The rc discipline in WITNESS_FORMAT.md: 0 all PASS, 1 a row FAILED, 2 malformed input.
Each probe records rc and the last stderr line. Seeded through fuzz_cases.build.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fuzz_cases import build  # noqa: E402

PROBES = [  # (name, mutations, extra table text or None, rc the spec calls for)
    ("valid", [], None, 0),
    ("c_as_list", ["c_as_list"], None, 2),
    ("lam_val_inf", ["lam_val_inf"], None, 2),
    ("lam_val_nan", ["lam_val_nan"], None, 2),
    ("lam_idx_bool", ["lam_idx_bool"], None, None),
    ("row_key_alias", ["row_key_alias"], None, None),
    ("row_float_frac", ["row_float_frac"], None, 2),
    ("table_not_json", [], "not json", 2),
    ("table_row_not_object", [], '{"1": "x"}', 2),
]


def main(bl, out):
    os.makedirs(out, exist_ok=True)
    tool = os.path.join(bl, "tools", "trust", "receipt", "receipt.py")
    res = []
    for name, muts, table_text, want in PROBES:
        s, w, _ = build(20261002, 0, "cli", muts, (2, 3))
        d = os.path.join(out, name)
        os.makedirs(d, exist_ok=True)
        for fn, txt in (("system.jsonl", s), ("w_x.json", w)):
            with open(os.path.join(d, fn), "w", encoding="utf-8", newline="") as fh:
                fh.write(txt)
        args = [sys.executable, tool, "verify", "--system-jsonl", os.path.join(d, "system.jsonl"),
                "--witness", os.path.join(d, "w_x.json"), "-q"]
        if table_text is not None:
            with open(os.path.join(d, "table.json"), "w", encoding="utf-8") as fh:
                fh.write(table_text)
            args += ["--table", os.path.join(d, "table.json")]
        r = subprocess.run(args, capture_output=True, text=True)
        last = (r.stderr.strip().splitlines() or [""])[-1]
        last = last.replace(d, "<case>").replace(d.replace(os.sep, "/"), "<case>")
        res.append({"probe": name, "rc": r.returncode, "rc_spec": want, "traceback": "Traceback" in r.stderr,
                    "stderr_last": last[:200], "stdout_head": r.stdout.strip()[:160]})
        print(name, r.returncode, want, last[:100], flush=True)
    with open(os.path.join(out, "cli_probe.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

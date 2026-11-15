"""Replace machine-local paths in a copied results folder and rewrite SHA256SUMS.

    python scripts/sanitize_results.py RESULTS_DIR

Paths become <bootloops>, <repo>, <out> or <path>. Verdicts and numbers are
untouched. SHA256SUMS is recomputed over the sanitized files.
"""
import hashlib
import os
import re
import sys

BS = chr(92)
SEP = "[" + BS + BS + "/]+"
SUBS = [
    ("C:" + SEP + "Users" + SEP + "[^" + BS + BS + "/]+" + SEP + "AppData" + SEP + "Local" + SEP + "Temp"
     + SEP + "claude" + SEP + "C--dev" + SEP + "[0-9a-f-]+" + SEP + "scratchpad" + SEP + "bootloops"
     + SEP + "bootloops", "<bootloops>"),
    ("D:" + SEP + "bootloops-second-checker", "<repo>"),
    ("/root/bsc-run/OUT/bootloops", "<bootloops>"),
    ("/root/bsc-run/repo", "<repo>"),
    ("/root/bsc-run/(?:OUT|EXT)", "<out>"),
    ("D:" + SEP + "bootloops-work", "<out>"),
    ("/mnt/[cd]/[^\\s\"]*", "<path>"),
    ("[A-Za-z]:(?:" + BS + BS + "|/)[^\\s\"]*", "<path>"),
]


def main(root):
    n = 0
    files = []
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            if f == "SHA256SUMS":
                continue
            files.append(p)
            with open(p, encoding="utf-8", errors="replace") as fh:
                t = fh.read()
            o = t
            for a, b in SUBS:
                t = re.sub(a, b, t)
            if t != o:
                with open(p, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(t)
                n += 1
    lines = []
    for p in files:
        with open(p, "rb") as fh:
            h = hashlib.sha256(fh.read()).hexdigest()
        lines.append((os.path.relpath(p, root).replace(BS, "/"), h))
    with open(os.path.join(root, "SHA256SUMS"), "w", encoding="utf-8", newline="\n") as fh:
        for rel, h in sorted(lines):
            fh.write(f"{h}  {rel}\n")
    print("sanitized", n, "files; hashed", len(lines))


if __name__ == "__main__":
    main(sys.argv[1])

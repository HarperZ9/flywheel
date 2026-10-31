"""Append one entry in the FINDINGS.md format: heading, date and status, summary, evidence,
reintegrated, scope. Numbers in the summary come from the run result through a template,
never typed by hand: "{analysis.log_loss.density:.3f}" reads that path and formats it.

Entries are only appended. The number is the highest '### <prefix>N.' already in the file plus one.
"""
import re
from pathlib import Path

from ..scope import LEGACY_SCOPE_KEY, scope_key, scope_of
from .hashing import short
from .verdict import get

HEAD = re.compile(r"^### ([A-Z]+)(\d+)\.", re.M)
FIELD = re.compile(r"\{([A-Za-z0-9_.]+)(?::([^}]+))?\}")


def render(template, result):
    def sub(m):
        v = get(result, m.group(1))
        return format(v, m.group(2)) if m.group(2) else str(v)
    return FIELD.sub(sub, template)


def next_number(text, prefix):
    nums = [int(n) for p, n in HEAD.findall(text) if p == prefix]
    return max(nums, default=0) + 1


def status_of(cfg, verdicts):
    flat = {k: v["verdict"] for k, v in verdicts.items()}
    for row in cfg.get("status_rules", []):
        if all(flat.get(k) == v for k, v in row["when"].items()):
            return row["status"]
    return "mixed: " + ", ".join(f"{k} {v}" for k, v in flat.items())


def _scope_line(cfg):
    """A spec names what the study covers under `scope`; a spec from the prototype keeps its limit wording."""
    label = "Does not prove" if scope_key(cfg) == LEGACY_SCOPE_KEY else "Scope"
    return f"- **{label}:** {scope_of(cfg)}"


def entry(spec, result, number, manifest_rel, manifest_sha):
    cfg = spec["ledger"]
    pre = result["prereg"]
    verdicts = ", ".join(f"{k} {v['verdict']}" for k, v in result["verdicts"].items())
    lines = [
        f"### {cfg.get('prefix', 'F')}{number}. {render(cfg.get('heading', spec['title']), result)}",
        f"- **Date:** {result['date']}. **Status:** {status_of(cfg, result['verdicts'])}, preregistered "
        f"({Path(pre['path']).name}, sha256 {short(pre['sha256'])}). Verdicts: {verdicts}.",
        f"- **Summary.** {render(cfg['summary'], result)}",
        f"- **Evidence:** `{manifest_rel}` (manifest sha256 {short(manifest_sha)}).",
        f"- **Reintegrated:** {cfg.get('reintegrated') or 'debt: not yet fed back into a tool'}.",
        _scope_line(cfg),
    ]
    if cfg.get("relates"):
        lines.insert(2, f"- **Relates to:** {cfg['relates']}")
    return "\n".join(lines) + "\n"


def append(spec, result, manifest_rel, manifest_sha):
    path = Path(spec["_ledger_path"])
    if not path.exists():
        path.write_text(spec["ledger"].get("header", "# Ledger\n") + "\n", encoding="utf-8", newline="\n")
    text = path.read_text(encoding="utf-8")
    number = next_number(text, spec["ledger"].get("prefix", "F"))
    block = entry(spec, result, number, manifest_rel, manifest_sha)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(("" if text.endswith("\n\n") else "\n") + block)
    return number, block

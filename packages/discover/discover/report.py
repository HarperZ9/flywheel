"""Findings, scores and the two output formats.

A finding is one check on one subject (a repository, a page, a video). It
passes or fails. A failed error blocks the gate; a failed warning lowers the
score and lists a fix, and does not block.
"""
from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict, dataclass, field

ERROR = "error"
WARN = "warn"
WEIGHT = {ERROR: 3, WARN: 1}


@dataclass
class Finding:
    check: str
    subject: str
    ok: bool
    severity: str = ERROR
    message: str = ""
    fix: str = ""


@dataclass
class Report:
    kind: str
    target: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, check: str, subject: str, ok: bool, severity: str = ERROR,
            message: str = "", fix: str = "") -> None:
        self.findings.append(Finding(check, subject, bool(ok), severity, message, fix))

    def extend(self, other: "Report") -> None:
        self.findings.extend(other.findings)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if not f.ok]

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.failures if f.severity == ERROR]

    @property
    def score(self) -> int:
        total = sum(WEIGHT[f.severity] for f in self.findings)
        if not total:
            return 100
        passed = sum(WEIGHT[f.severity] for f in self.findings if f.ok)
        return round(100 * passed / total)

    def passes(self, min_score: int = 0) -> bool:
        return not self.blocking and self.score >= min_score

    def to_json(self) -> str:
        body = {
            "kind": self.kind, "target": self.target, "score": self.score,
            "checks": len(self.findings), "failed": len(self.failures),
            "blocking": len(self.blocking),
            "findings": [asdict(f) for f in self.findings],
        }
        return json.dumps(body, indent=2, ensure_ascii=False)

    def to_text(self, limit: int = 8) -> str:
        lines = [f"discover {self.kind}: {self.target}",
                 f"score {self.score}/100  checks {len(self.findings)}  "
                 f"failed {len(self.failures)}  blocking {len(self.blocking)}"]
        groups: "OrderedDict[tuple[str, str], list[Finding]]" = OrderedDict()
        for f in self.failures:
            groups.setdefault((f.severity, f.check), []).append(f)
        ordered = sorted(groups.items(), key=lambda kv: (kv[0][0] != ERROR, kv[0][1]))
        if ordered:
            lines.append("")
            lines.append("fixes:")
        for (severity, check), items in ordered:
            lines.append(f"  [{severity}] {check} ({len(items)})")
            for f in items[:limit]:
                detail = f": {f.message}" if f.message else ""
                lines.append(f"    {f.subject}{detail}")
            if len(items) > limit:
                lines.append(f"    ... and {len(items) - limit} more (use --json for all)")
            if items[0].fix:
                lines.append(f"    fix: {items[0].fix}")
        return "\n".join(lines)

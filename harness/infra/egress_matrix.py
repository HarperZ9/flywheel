"""egress_matrix.py -- the allowlist matrix for network egress control.

Artifact 17 (Data-Flow and Egress Control Matrix) data layer. Defines which
outbound destinations are allowed, covering DNS, HTTP/HTTPS, package
registries, cloud metadata (169.254.169.254), and telemetry endpoints.

The matrix is loaded from JSON and machine-enforced. Default-deny mode flags
any connection not explicitly in the matrix.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Known dangerous destinations that should ALWAYS be flagged.
BLOCKED_BY_DEFAULT = [
    {"pattern": "169.254.169.254", "reason": "cloud metadata service"},
    {"pattern": "metadata.google.internal", "reason": "GCP metadata"},
    {"pattern": "169.254.170.2", "reason": "ECS task metadata"},
]

# Default-allowed destinations for a development environment.
DEFAULT_ALLOWED = [
    {"pattern": "127.0.0.1", "port": "*", "protocol": "*", "purpose": "localhost"},
    {"pattern": "localhost", "port": "*", "protocol": "*", "purpose": "localhost"},
    {"pattern": "*.pypi.org", "port": "443", "protocol": "https",
     "purpose": "python package registry"},
    {"pattern": "pypi.org", "port": "443", "protocol": "https",
     "purpose": "python package registry"},
    {"pattern": "registry.npmjs.org", "port": "443", "protocol": "https",
     "purpose": "npm package registry"},
]


@dataclass
class EgressRule:
    """One rule in the egress matrix."""
    pattern: str
    port: str = "*"
    protocol: str = "*"
    purpose: str = ""
    allowed: bool = True

    def matches(self, destination: str, port: int, protocol: str) -> bool:
        """Check if this rule matches a given connection."""
        if not self._match_pattern(destination):
            return False
        if self.port != "*" and str(port) != self.port:
            return False
        if self.protocol != "*" and protocol.lower() != self.protocol.lower():
            return False
        return True

    def _match_pattern(self, destination: str) -> bool:
        if self.pattern.startswith("*."):
            suffix = self.pattern[1:]
            return destination.endswith(suffix) or destination == self.pattern[2:]
        return destination == self.pattern


@dataclass
class EgressMatrix:
    """The egress control matrix. Default-deny when strict=True."""
    rules: list[EgressRule] = field(default_factory=list)
    strict: bool = False  # strict = default-deny (flag unknown destinations)

    def check(self, destination: str, port: int = 0,
              protocol: str = "tcp") -> dict[str, Any]:
        """Check a destination against the matrix.

        Returns {verdict, matched_rule, purpose}. Verdict is ALLOWED, BLOCKED,
        or UNKNOWN (only in non-strict mode; in strict mode UNKNOWN becomes
        BLOCKED).
        """
        for blocked in BLOCKED_BY_DEFAULT:
            if blocked["pattern"] in destination:
                return {"verdict": "BLOCKED", "reason": blocked["reason"],
                        "destination": destination, "port": port}

        for rule in self.rules:
            if rule.matches(destination, port, protocol):
                return {"verdict": "ALLOWED" if rule.allowed else "BLOCKED",
                        "destination": destination, "port": port,
                        "purpose": rule.purpose}

        verdict = "BLOCKED" if self.strict else "UNKNOWN"
        return {"verdict": verdict, "destination": destination, "port": port,
                "reason": "not in matrix"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "strict": self.strict,
            "rules": [
                {"pattern": r.pattern, "port": r.port, "protocol": r.protocol,
                 "purpose": r.purpose, "allowed": r.allowed}
                for r in self.rules
            ],
        }


def default_matrix(strict: bool = False) -> EgressMatrix:
    """Create the default egress matrix for a Flywheel development environment."""
    rules = [EgressRule(**r) for r in DEFAULT_ALLOWED]
    return EgressMatrix(rules=rules, strict=strict)


def load_matrix(path: Path) -> EgressMatrix:
    """Load an egress matrix from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = [EgressRule(**r) for r in data.get("rules", [])]
    return EgressMatrix(rules=rules, strict=data.get("strict", False))

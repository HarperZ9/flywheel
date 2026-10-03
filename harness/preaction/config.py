"""config.py -- the monitor's owner-set configuration and its digest.

The config is hashable to one monitor_config_sha256. The owner pins it; a later
change makes every call BLOCK until the owner re-pins, so nobody can quietly
soften the monitor. Every record carries the digest, so a change shows as a
break in the recorded digest sequence.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contract import canonical_json, sha256_hex
from .judge import HttpJudge, JudgeConfig
from .optional_rules import with_optional


@dataclass
class MonitorConfig:
    rules_overlay: dict | None = None
    judge: JudgeConfig | None = None
    judge_threshold: int = 3
    judge_unavailable: str = "hold"       # "hold" (default) or "allow"
    hold_expiry_minutes: int = 30
    drift_threshold: int = 5
    strict_judge_reads: bool = True       # judge reads too; owner may narrow
    owner_sha256: str = ""                # set when an owner file is loaded (owner.py)

    @classmethod
    def from_dict(cls, d: dict) -> "MonitorConfig":
        j = d.get("judge") or {}
        judge = JudgeConfig(**j) if j else None
        if judge is not None:
            judge.resolved_mode()  # an impossible protocol and mode pair fails at load
        overlay = d.get("rules_overlay")
        optional = d.get("optional_rules") or []
        if not isinstance(optional, list):
            raise ValueError("optional_rules must be a list of overlay names")
        if optional:
            overlay = with_optional(overlay, *optional)
        return cls(rules_overlay=overlay, judge=judge,
                   judge_threshold=int(d.get("judge_threshold", 3)),
                   judge_unavailable=d.get("judge_unavailable", "hold"),
                   hold_expiry_minutes=int(d.get("hold_expiry_minutes", 30)),
                   drift_threshold=int(d.get("drift_threshold", 5)),
                   strict_judge_reads=bool(d.get("strict_judge_reads", True)))

    def build_judges(self) -> list:
        if not self.judge or not self.judge.model:
            return []
        if self.judge.resolved_mode() == "typed":
            from .judge_typed import SystemOneJudge
            return [SystemOneJudge(self.judge)]
        return [HttpJudge(self.judge)]

    def digest(self) -> str:
        body = self._digest_body()
        if self.owner_sha256:
            # Present only with an owner file, so a monitor with no owner file
            # keeps the digest it had before owner files existed.
            body["owner_sha256"] = self.owner_sha256
        return sha256_hex(canonical_json(body))

    def _judge_digest(self) -> dict:
        body = {"endpoint": getattr(self.judge, "endpoint", ""),
                "model": getattr(self.judge, "model", "")}
        if self.judge is not None and self.judge.protocol != "openai":
            # Only a non-default protocol joins the digest, so every config
            # written before typed mode existed keeps the digest it was pinned at.
            body["protocol"] = self.judge.protocol
            body["mode"] = self.judge.resolved_mode()
        elif self.judge is not None and self.judge.mode:
            body["mode"] = self.judge.mode
        return body

    def _digest_body(self) -> dict:
        return dict({
            "rules_overlay": self.rules_overlay or {},
            "judge": self._judge_digest(),
            "judge_threshold": self.judge_threshold,
            "judge_unavailable": self.judge_unavailable,
            "hold_expiry_minutes": self.hold_expiry_minutes,
            "drift_threshold": self.drift_threshold,
            "strict_judge_reads": self.strict_judge_reads})

"""Materialize the transcript fixtures for one test: fill the project root and
plant secret-shaped values that are built here at run time, so no committed
file carries a string a secret scanner would flag."""
from __future__ import annotations

import json
from pathlib import Path

TRANSCRIPTS = Path(__file__).parent / "fixtures" / "transcripts"


def planted() -> dict[str, str]:
    """One value per scrubber rule the fixtures exercise. Every value is a
    canary: the tests assert it never appears in a stored or rendered byte."""
    return {
        "OPENAI": "sk-proj-" + "CanaryOpenAI" + "q" * 24,
        "ANTHROPIC": "sk-ant-api03-" + "CanaryAnthropic" + "w" * 24,
        "GITHUB": "ghp_" + "CanaryGitHub" + "e" * 26,
        "AWS": "AKIA" + "CANARYAWSKEY0001",
        "BEARER": "canaryBearerToken" + "r" * 16,
        "PASSWORD": "canary-db-password-77",
        "GENERIC": "canary-env-value-88",
        "KEYBODY": "MIIEcanaryPrivateKeyBody" + "t" * 20,
        "JSONSECRET": "canary-json-secret-99",
    }


def materialize(tmp_path: Path, name: str, *, root: Path, remote: str = "",
                values: dict[str, str] | None = None) -> Path:
    text = (TRANSCRIPTS / name).read_text(encoding="utf-8")
    fills = {"ROOT": str(root), "OUTSIDE": str(tmp_path / "elsewhere"),
             "REMOTE": remote, **(values if values is not None else planted())}
    for key, value in fills.items():
        text = text.replace("{{" + key + "}}", json.dumps(value)[1:-1])
    out = tmp_path / name
    out.write_text(text, encoding="utf-8", newline="\n")
    return out


def every_stored_byte(root: Path) -> str:
    """The text of every file under a store root, for canary checks."""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.rglob("*"))
                     if p.is_file() and p.suffix in (".jsonl", ".json"))

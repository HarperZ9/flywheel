"""redaction-contract family: public-safe secret redaction fixtures.

The raw values in this family are synthetic markers. The contract is still the
real behavior the fixture is meant to pin: preserve provenance metadata, replace
raw secret values everywhere they appear in terminal JSON output, and retain
safe secret references so rerun instructions stay useful.
"""

from __future__ import annotations

from dataclasses import dataclass

POLICY = "redaction-contract/1"
SECRET_PREFIX = "FAKE_SECRET_DO_NOT_USE_LOOP29"


@dataclass(frozen=True)
class RedactionVariant:
    variant_id: str
    title: str
    purpose: str


_VARIANTS: tuple[RedactionVariant, ...] = (
    RedactionVariant(
        "redact-00-headers",
        "header and CLI output redaction",
        "raw header values leak through config, stdout, stderr, and logs",
    ),
    RedactionVariant(
        "redact-01-overlap",
        "overlapping secret values",
        "longer secret values must be replaced before shorter prefixes",
    ),
    RedactionVariant(
        "redact-02-refs",
        "secret references without raw values",
        "safe references survive while raw values are removed",
    ),
    RedactionVariant(
        "redact-03-manifest",
        "artifact manifest provenance",
        "hashes, labels, and public metadata survive redaction",
    ),
)


def all_variants() -> list[RedactionVariant]:
    return list(_VARIANTS)


def _secret(name: str) -> str:
    return f"{SECRET_PREFIX}_{name}"


def _base_record(cell: str, secrets: list[dict], **fields) -> dict:
    record = {
        "schema": "redaction.fixture.input/1",
        "case_id": cell,
        "secrets": secrets,
    }
    record.update(fields)
    return record


def fixtures_for(variant: RedactionVariant) -> list[dict]:
    """Hidden scored inputs for one variant. Inputs are committed because they
    are synthetic; expected redacted terminal states are generated from the
    reference and are separately scanned for raw marker absence."""
    if variant.variant_id == "redact-00-headers":
        auth = _secret("AUTH")
        api = _secret("API")
        secrets = [
            {"name": "AUTH_TOKEN", "value": auth, "source": "env:AUTH_TOKEN"},
            {"name": "API_KEY", "value": api, "source": "env:API_KEY"},
        ]
        return [
            {
                "cell": "header-value",
                "record": _base_record(
                    "header-value",
                    secrets,
                    config={
                        "endpoint": "https://example.invalid/eval",
                        "headers": {
                            "Authorization": f"Bearer {auth}",
                            "X-Trace": "trace-public-001",
                        },
                    },
                ),
            },
            {
                "cell": "stdout-stderr",
                "record": _base_record(
                    "stdout-stderr",
                    secrets,
                    stdout=f"AUTH={auth}\nfinished",
                    stderr=f"retry with API key {api}",
                ),
            },
            {
                "cell": "log-list",
                "record": _base_record(
                    "log-list",
                    secrets,
                    log=[
                        "request accepted",
                        f"debug token={auth}",
                        {"line": f"api={api}", "level": "debug"},
                    ],
                ),
            },
            {
                "cell": "secret-table",
                "record": _base_record(
                    "secret-table",
                    secrets,
                    config={"api_key": api, "mode": "dry-run"},
                ),
            },
            {
                "cell": "public-values",
                "record": _base_record(
                    "public-values",
                    secrets,
                    manifest={"sha256": "0" * 64, "path_label": "artifact:stdout"},
                    note="public metadata stays readable",
                ),
            },
        ]

    if variant.variant_id == "redact-01-overlap":
        short = _secret("TOKEN")
        long = _secret("TOKEN_EXTRA")
        secrets = [
            {"name": "SHORT", "value": short, "source": "env:SHORT"},
            {"name": "LONG", "value": long, "source": "env:LONG"},
        ]
        return [
            {
                "cell": "long-first",
                "record": _base_record(
                    "long-first",
                    secrets,
                    stdout=f"winner {long}",
                ),
            },
            {
                "cell": "both-values",
                "record": _base_record(
                    "both-values",
                    secrets,
                    log=[f"short={short}", f"long={long}"],
                ),
            },
            {
                "cell": "adjacent",
                "record": _base_record(
                    "adjacent",
                    secrets,
                    stderr=f"{long}:{short}",
                ),
            },
            {
                "cell": "nested",
                "record": _base_record(
                    "nested",
                    secrets,
                    config={"tokens": [{"raw": long}, {"raw": short}]},
                ),
            },
            {
                "cell": "non-secret-prefix",
                "record": _base_record(
                    "non-secret-prefix",
                    secrets,
                    stdout="TOKEN is a public word when the raw value is absent",
                ),
            },
        ]

    if variant.variant_id == "redact-02-refs":
        auth = _secret("REF_AUTH")
        secrets = [{"name": "AUTH_TOKEN", "value": auth, "source": "env:AUTH_TOKEN"}]
        return [
            {
                "cell": "secret-ref-object",
                "record": _base_record(
                    "secret-ref-object",
                    secrets,
                    config={"authorization": {"secret_ref": "AUTH_TOKEN"}},
                ),
            },
            {
                "cell": "ref-plus-raw",
                "record": _base_record(
                    "ref-plus-raw",
                    secrets,
                    config={"authorization": {"secret_ref": "AUTH_TOKEN"}},
                    log=[f"debug raw {auth}", "rerun with secret_ref AUTH_TOKEN"],
                ),
            },
            {
                "cell": "missing-secret-list",
                "record": {
                    "schema": "redaction.fixture.input/1",
                    "case_id": "missing-secret-list",
                    "config": {"authorization": {"secret_ref": "AUTH_TOKEN"}},
                    "log": ["no raw value supplied"],
                },
            },
            {
                "cell": "empty-value-ignored",
                "record": _base_record(
                    "empty-value-ignored",
                    [{"name": "EMPTY", "value": "", "source": "env:EMPTY"}],
                    stdout="nothing to redact",
                ),
            },
            {
                "cell": "numbers-and-bools",
                "record": _base_record(
                    "numbers-and-bools",
                    secrets,
                    metrics={"attempts": 3, "accepted": False, "cost": None},
                ),
            },
        ]

    if variant.variant_id == "redact-03-manifest":
        session = _secret("SESSION")
        secrets = [
            {"name": "SESSION_KEY", "value": session, "source": "env:SESSION_KEY"}
        ]
        return [
            {
                "cell": "manifest-public",
                "record": _base_record(
                    "manifest-public",
                    secrets,
                    manifest={
                        "path_label": "artifact:manifest",
                        "sha256": "a" * 64,
                        "bytes": 128,
                        "collection_status": "collected",
                    },
                ),
            },
            {
                "cell": "manifest-command",
                "record": _base_record(
                    "manifest-command",
                    secrets,
                    manifest={"rerun": f"SESSION_KEY={session} run-eval"},
                ),
            },
            {
                "cell": "multi-artifact",
                "record": _base_record(
                    "multi-artifact",
                    secrets,
                    artifacts=[
                        {
                            "path_label": "artifact:stdout",
                            "preview": f"session={session}",
                        },
                        {"path_label": "artifact:stderr", "preview": "no secret"},
                    ],
                ),
            },
            {
                "cell": "audit-note",
                "record": _base_record(
                    "audit-note",
                    secrets,
                    audit={"decision": "not_executed", "reason": f"missing {session}"},
                ),
            },
            {
                "cell": "stable-hash",
                "record": _base_record(
                    "stable-hash",
                    secrets,
                    manifest={"sha256": "f" * 64, "path_label": "artifact:input"},
                ),
            },
        ]

    raise ValueError(f"unknown redaction variant: {variant.variant_id}")


def worked_for(variant: RedactionVariant) -> list[dict]:
    slug = variant.variant_id.replace("-", "_").upper()
    raw = _secret(f"WORKED_{slug}_TOKEN")
    secrets = [
        {
            "name": "WORKED_TOKEN",
            "value": raw,
            "source": "env:WORKED_TOKEN",
        }
    ]
    records = [
        _base_record(
            f"worked-{variant.variant_id}-stdout",
            secrets,
            stdout=f"rerun with WORKED_TOKEN={raw}",
            trace_id=f"trace-worked-{variant.variant_id}-001",
        ),
        _base_record(
            f"worked-{variant.variant_id}-manifest",
            secrets,
            manifest={
                "path_label": "artifact:worked",
                "sha256": "b" * 64,
                "rerun": f"WORKED_TOKEN={raw} run-fixture",
            },
        ),
    ]
    out = []
    for record in records:
        worked = {
            "cell": record["case_id"],
            "record": record,
            "expect": reference_redact(record),
        }
        out.append(worked)
    return out


def _secret_pairs(record: dict) -> list[tuple[str, str]]:
    rows = record.get("secrets") or []
    pairs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        value = row.get("value")
        if isinstance(name, str) and isinstance(value, str) and value:
            pairs.append((name, value))
    return sorted(pairs, key=lambda item: len(item[1]), reverse=True)


def _walk(value, pairs: list[tuple[str, str]]):
    if isinstance(value, str):
        text = value
        for name, raw in pairs:
            text = text.replace(raw, f"<redacted:{name}>")
        return text
    if isinstance(value, list):
        return [_walk(item, pairs) for item in value]
    if isinstance(value, dict):
        return {str(key): _walk(item, pairs) for key, item in value.items()}
    return value


def reference_redact(record: dict) -> dict:
    out = _walk(record, _secret_pairs(record))
    if not isinstance(out, dict):
        raise TypeError("record must be a dict")
    out["redaction_policy"] = POLICY
    return out


def reference_module_source() -> str:
    return """POLICY = "redaction-contract/1"

def _secret_pairs(record):
    rows = record.get("secrets") or []
    pairs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        value = row.get("value")
        if isinstance(name, str) and isinstance(value, str) and value:
            pairs.append((name, value))
    return sorted(pairs, key=lambda item: len(item[1]), reverse=True)

def _walk(value, pairs):
    if isinstance(value, str):
        text = value
        for name, raw in pairs:
            text = text.replace(raw, f"<redacted:{name}>")
        return text
    if isinstance(value, list):
        return [_walk(item, pairs) for item in value]
    if isinstance(value, dict):
        return {str(key): _walk(item, pairs) for key, item in value.items()}
    return value

def redact_record(record):
    out = _walk(record, _secret_pairs(record))
    out["redaction_policy"] = POLICY
    return out
"""

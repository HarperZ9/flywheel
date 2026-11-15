"""Best-effort demo -- not runtime-verified by author.

End-to-end demo of the model-provenance-validator Python API.

It builds a provenance envelope in memory, validates it against the bundled
schema, prints the result, then mutates the envelope into an invalid one and
prints the specific validation errors. Every function used here is part of the
public surface exported from ``model_provenance_validator``.

Run it with the package importable, e.g.:

    python examples/demo.py

(from a clone with ``src`` on PYTHONPATH, or after ``pip install -e .``).
"""

from __future__ import annotations

from model_provenance_validator import (
    load_schema,
    validate_envelope,
)


def report(label: str, envelope: dict) -> None:
    schema = load_schema()  # bundled schema
    errors = validate_envelope(envelope, schema)
    if not errors:
        print(f"{label}: valid")
        return
    print(f"{label}: invalid")
    for error in errors:
        # error is a ValidationError with .path and a redacted .message
        print(f"  {error.path}: {error.message}")


def main() -> None:
    # A well-formed provenance envelope (matches the bundled schema).
    envelope = {
        "envelope_version": "1",
        "subject": "model-provenance-validator README usage claim",
        "source": {
            "name": "Repository README",
            "kind": "release-note",
        },
        "references": [
            {
                "name": "Repository README",
                "locator": "https://github.com/HarperZ9/model-provenance-validator",
                "retrieved_at": "2026-06-18",
            }
        ],
        "validation": {
            "status": "verified",
            "notes": "Claim checked against the public README surface.",
        },
    }

    report("valid-envelope", envelope)

    # Now break it: empty references and an out-of-enum source kind.
    broken = {
        **envelope,
        "references": [],
        "source": {"name": "Some blog", "kind": "blog"},
    }
    report("broken-envelope", broken)


if __name__ == "__main__":
    main()

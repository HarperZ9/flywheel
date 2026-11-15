from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


RECORDS_JSONL = (
    '{"canon_schema":"canon.record/v1","data":{"body":"Keep facts bounded.","title":"Voice"},'
    '"id":"voice-canon","kind":"personality-block","provenance":{"create_ord":1,'
    '"create_time":null,"harness":"synthetic","model_slug":"none",'
    '"native_id":"block:voice-canon","session_id":null,'
    '"source_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
    '"scope":"workspace","temporal":{"supersedes":null,"valid_until":null}}\n'
)

ATOMS_JSONL = "\n".join(
    [
        (
            '{"atom_schema":"canon.atom/v1","classification":"normative","critical":true,'
            '"disclosure":{"profile":"project-only"},"freshness":{"state":"current"},'
            '"hashes":{},"id":"goal-migrate","layer":"session","precedence_rank":0,'
            '"scope_key":"workspace:canon","source_refs":[{"ref":"record:voice-canon"}],'
            '"source_span_refs":[],"status":"active","trust":{"label":"trusted-local"},'
            '"type":"active-goal","value":{"summary":"Move a provider-neutral handoff into Canon."}}'
        ),
        "",
    ]
)


def _run(argv: list[str]) -> tuple[int, str, str]:
    from canon.cli import run_cli

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def test_source_parent_swap_after_resolution_refuses_outside_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import canon.cli_artifacts as cli_artifacts

    workspace = tmp_path / "work"
    source_dir = workspace / "sources"
    outside_dir = tmp_path / "outside" / "sources"
    displaced = tmp_path / "displaced-sources"
    source_dir.mkdir(parents=True)
    outside_dir.mkdir(parents=True)
    (source_dir / "records.jsonl").write_text(RECORDS_JSONL, encoding="utf-8")
    (workspace / "atoms.jsonl").write_text(ATOMS_JSONL, encoding="utf-8")
    (outside_dir / "records.jsonl").write_text(
        RECORDS_JSONL.replace("Keep facts bounded.", "outside-source-canary"),
        encoding="utf-8",
    )
    real_resolve = cli_artifacts.resolve_under_root
    attempted = False

    def swap_after_resolution(path: object, **kwargs: object) -> Path:
        nonlocal attempted
        resolved = real_resolve(path, **kwargs)
        if path == "sources/records.jsonl" and not attempted:
            attempted = True
            source_dir.rename(displaced)
            try:
                source_dir.symlink_to(outside_dir, target_is_directory=True)
            except OSError:
                pytest.skip("current platform or privileges do not allow directory symlinks")
        return resolved

    monkeypatch.setattr(cli_artifacts, "resolve_under_root", swap_after_resolution)

    code, stdout, stderr = _run([
        "--json",
        "preview",
        "--workspace",
        str(workspace),
        "--records",
        "sources/records.jsonl",
        "--atoms",
        "atoms.jsonl",
        "--target",
        "codex-cli",
    ])

    assert attempted
    assert code == 4
    assert stderr == ""
    assert json.loads(stdout)["failure_code"] == "unsafe_path"
    assert "outside-source-canary" not in stdout + stderr

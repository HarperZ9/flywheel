"""OS-enforced read-only execution namespace for a child verifier."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path

PROTECTION = "windows-low-integrity-namespace/v1"


class ExecutionInputProtectionUnavailable(RuntimeError):
    """The host cannot establish the execution-input invariant."""


@contextmanager
def protect_execution_namespace(input_root: Path, output_root: Path):
    """Run a low-integrity child over medium-integrity inputs and low output.

    The input and output roots are siblings by contract. The child can read the
    former but cannot write, delete, replace, or create anywhere beneath it.
    JUnit, temp, and provenance output go only to the separately admitted low-
    integrity root. Unsupported hosts fail before a child is created.
    """
    if os.name != "nt":
        raise ExecutionInputProtectionUnavailable(
            "this host has no OS-enforced child-read-only import namespace")
    source = Path(input_root).resolve(strict=True)
    output = Path(output_root).resolve(strict=True)
    if (source.parent != output.parent or source == output
            or source in output.parents or output in source.parents
            or not source.is_dir() or not output.is_dir() or any(output.iterdir())):
        raise ExecutionInputProtectionUnavailable(
            "execution input and output must be distinct empty sibling directories")
    try:
        from .windows_low_integrity import LowIntegrityRunner
        with LowIntegrityRunner(source, output) as runner:
            yield runner
    except ExecutionInputProtectionUnavailable:
        raise
    except Exception as exc:
        raise ExecutionInputProtectionUnavailable(
            f"Windows namespace protection failed ({type(exc).__name__})") from exc

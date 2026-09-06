"""The POSIX sandbox as the harness actually reaches it.

The builder tests next door prove what the argv and the profile say. These
prove that the shipped entry point routes through them, that what it hands
the child agrees with what the policy permits, and, where a backend exists,
that the kernel enforces what the record claims. A backend nobody calls
would pass every test in the other file and confine nothing.
"""
import os
from types import SimpleNamespace

import pytest

from harness.posix_sandbox import Confinement, backend_for, posix_run


def posix_host(monkeypatch, module):
    """Make the module believe it is on a POSIX host.

    The name is read off the module's own `os`, not off the interpreter's.
    Setting `os.name` itself would change which concrete Path class pathlib
    builds, and the test would fail on a detail the code never touches.
    """
    monkeypatch.setattr(
        module, "os", SimpleNamespace(name="posix", environ=os.environ))


def test_the_shipped_entry_point_refuses_when_this_host_has_no_backend(
        monkeypatch, tmp_path):
    # Reached through sandboxed_run, not through the module under test. A
    # backend nobody calls would pass every test above and confine nothing.
    #
    # Both halves of the condition are forced. Routing to the POSIX path is
    # not the same as having no backend there, and on macOS it is not even
    # correlated: `sandbox-exec` ships with the OS, so this test passed on
    # Windows and Linux by accident and failed on the one host where the
    # name it carries was a live question.
    from harness import posix_sandbox, sandboxed_runner
    posix_host(monkeypatch, sandboxed_runner)
    monkeypatch.setattr(posix_sandbox, "backend_for", lambda *a, **k: None)
    with pytest.raises(sandboxed_runner.SandboxUnavailable) as stop:
        sandboxed_runner.sandboxed_run("echo hi", str(tmp_path))
    assert "no sandbox backend" in str(stop.value)


def test_the_posix_path_labels_its_output_and_redacts_what_it_was_bound(
        monkeypatch, tmp_path):
    # Two claims the Windows path already makes, checked on the new one: a
    # bound value may not come back in the output, and the backend that ran
    # is named where a reader of the transcript will see it.
    from harness import posix_sandbox, sandboxed_runner
    from harness.credential_handles import CredentialBindings
    plan = Confinement(backend="bwrap", program="bwrap", root=str(tmp_path),
                       writable=(str(tmp_path),), network=True,
                       processes_isolated=True)
    posix_host(monkeypatch, sandboxed_runner)
    monkeypatch.setattr(posix_sandbox, "posix_run",
                        lambda *a, **k: (0, "token=s3cret", plan))
    ok, out = sandboxed_runner.sandboxed_run(
        "printenv TOKEN", str(tmp_path),
        bindings=CredentialBindings({"TOKEN": "s3cret"}))
    assert ok
    assert "s3cret" not in out
    assert "[sandbox bwrap:" in out
    # The parity argument made at the call site: the Windows backend cannot
    # restrict the network, so this one does not either by default.
    assert "network allowed" in out


def test_the_child_is_told_to_put_its_temp_files_where_it_can_write_them(
        monkeypatch, tmp_path):
    """The other half of dropping the blanket temp allowance.

    Once the policy stops allowing the system temp directory, a child that
    inherits the host's `TMPDIR` is pointed at a path the kernel refuses.
    The three names have to arrive holding the scratch directory the backend
    binds writable, and it has to be the same directory, not one spelled
    differently.
    """
    from harness import posix_sandbox, sandboxed_runner
    seen = {}

    def capture(cmd, root, work, **kwargs):
        seen["work"] = work
        seen["env"] = kwargs["env"]
        return 0, "", Confinement(backend="bwrap", program="bwrap",
                                  root=str(root), writable=(str(root),
                                                            str(work)))

    posix_host(monkeypatch, sandboxed_runner)
    monkeypatch.setattr(posix_sandbox, "posix_run", capture)
    monkeypatch.setenv("TMPDIR", "/somewhere/the/policy/denies")
    sandboxed_runner.sandboxed_run("true", str(tmp_path))
    for name in ("TMPDIR", "TMP", "TEMP"):
        assert seen["env"][name] == str(seen["work"]), (
            f"{name} points outside the sandbox, so a toolchain that reads "
            f"it writes to a path the policy denies")
    # Resolved, or the profile carries a spelling the kernel never matches.
    assert seen["work"] == seen["work"].resolve()


@pytest.mark.skipif(backend_for() is None,
                    reason="this host has no POSIX sandbox backend")
def test_a_real_confined_run_on_this_host(tmp_path):
    # The only test here that proves the policy rather than the string. It
    # runs where a backend exists and skips where none does, which is the
    # same answer the shipped code gives.
    work = tmp_path / "scratch"
    work.mkdir()
    rc, out, plan = posix_run("echo confined > out.txt && cat out.txt",
                              tmp_path, work, env={"PATH": os.environ["PATH"]},
                              network=True)
    assert rc == 0, out
    assert "confined" in out
    assert (tmp_path / "out.txt").read_text().strip() == "confined"
    assert plan.backend == backend_for()


@pytest.mark.skipif(backend_for() is None,
                    reason="this host has no POSIX sandbox backend")
def test_a_real_run_cannot_write_outside_the_workspace(tmp_path):
    # The claim the record makes, tested against the filesystem.
    work, outside = tmp_path / "scratch", tmp_path / "outside"
    work.mkdir()
    outside.mkdir()
    inside = tmp_path / "repo"
    inside.mkdir()
    rc, out, _ = posix_run(f"echo escaped > {outside}/leak.txt",
                           inside, work, env={"PATH": os.environ["PATH"]},
                           network=True)
    assert rc != 0, out
    assert not (outside / "leak.txt").exists()

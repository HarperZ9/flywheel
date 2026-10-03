"""Presence verifiers (7.15). Each has a `name` and `ask(summary) -> bool`.

- `windows-hello`: Windows' `UserConsentVerifier` asks for the owner's PIN,
  fingerprint or face with the summary as its message. The gateway runs a
  fixed inline PowerShell script, never a script file an agent could replace,
  and passes the summary on stdin. Whether it works from a non-packaged
  process, surfaces in front, and resists same-integrity input for a known PIN
  is experiment X7, a manual check; no automated test runs the real prompt.
- `desktop-dialog` is retired: no dialog was built, and approving over the
  bearer-token route would have let any process holding the token approve.
  A method file that still names it reads as `none`.
- `none`: a typed confirmation at the CLI, or nothing over the authenticated
  route. An agent can type too; the records say so.
"""
from __future__ import annotations

import subprocess
import sys

_HELLO_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
    "$m=[Console]::In.ReadToEnd();"
    "$null=[Windows.Security.Credentials.UI.UserConsentVerifier,"
    "Windows.Security.Credentials.UI,ContentType=WindowsRuntime];"
    "$t=([System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object{"
    "$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
    "$_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'})[0];"
    "$op=[Windows.Security.Credentials.UI.UserConsentVerifier]::RequestVerificationAsync($m);"
    "$task=$t.MakeGenericMethod([Windows.Security.Credentials.UI."
    "UserConsentVerificationResult]).Invoke($null,@($op));"
    "$null=$task.Wait(120000);[Console]::Out.Write($task.Result.ToString())")


def _powershell() -> str:
    """Windows PowerShell from System32, never a powershell.exe in the working folder."""
    from .safe_program import system_tool
    return system_tool(r"WindowsPowerShell\v1.0\powershell.exe")


class WindowsHelloVerifier:
    name = "windows-hello"

    def __init__(self, runner=None) -> None:
        self.runner = runner or subprocess.run

    def ask(self, summary: str) -> bool:
        if sys.platform != "win32":
            return False
        try:
            done = self.runner([_powershell(), "-NoProfile", "-NonInteractive",
                                "-Command", _HELLO_SCRIPT], input=summary.encode("utf-8"),
                               capture_output=True, timeout=150)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return done.returncode == 0 and done.stdout.strip() == b"Verified"


class NoneVerifier:
    name = "none"

    def __init__(self, interactive: bool = False, reader=None, writer=print) -> None:
        self.interactive, self.reader, self.writer = interactive, reader, writer

    def ask(self, summary: str) -> bool:
        if not self.interactive:
            return True
        self.writer(summary)
        self.writer("No presence method is set up: any process running as you can answer "
                    "this. Type yes to continue.")
        return (self.reader or input)().strip().lower() == "yes"


def verifier_for(method: str, *, interactive: bool = False):
    if method == "windows-hello":
        return WindowsHelloVerifier()
    return NoneVerifier(interactive=interactive)

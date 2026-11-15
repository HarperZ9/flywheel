# Native local Articulate package

The Windows x64 development package runs Articulate's local MCP tools with its
own bundled Python runtime. Your connected client's model supplies rewritten
text through `edit_plan` and `edit_submit`, so the package runs on your machine
with no API key or hosted service.

The portable ZIP and Claude Desktop MCPB contain the same executable and license
files. Extract the ZIP and set your local MCP client's executable to
`server/articulate-local.exe`, with an empty argument list. Clients supporting
binary MCPB extensions can read the included manifest. The executable refuses
arguments and sets local-only mode before loading Articulate, so inherited
settings leave model backends off. Connecting and installing it in each client
is still to be checked.

## Build and check a development candidate

From this repository, run the following with an isolated Windows x64 Python
environment that already has PyInstaller installed. `OUTPUT` is a new folder
the build creates.

```text
python scripts/build_native_articulate.py OUTPUT --mode dev
```

The builder runs the native protocol check before creating archives. It isolates
DLL discovery from ambient PATH, records native dependency origins, freezer
versions and source hashes, and rejects a dependency outside the Python runtime.
It includes the Python distribution's license and third-party notices, including
its Microsoft distributable-code terms, plus the PyInstaller bootloader license.
It does not copy runtime DLLs from System32. The archive rejects unexpected files,
links, reparse points, non-x64 executables, unsafe versions and output overwrites.
Archives reproduce identical bytes from the same payload; the compiler output
itself is not claimed to be reproducible across machines or rebuilds.

The protocol check runs with Python absent from PATH and conflicting inherited
settings. It checks local tool discovery, prose checking, host edit acceptance,
changed-number refusal and explicit backend refusal. This verifies the executable
on the build machine. It does not prove clean Windows installation, marketplace
acceptance, global network isolation or semantic equivalence of accepted edits.

## Release boundary

The default build and archive mode is `release`. It refuses source with changed
or untracked files, mismatched package or plugin versions, a version not ending
in `.0`, or a HEAD that differs from the exact version tag. CI must also be
running on that tag. The reviewed release-line detector must remain unchanged.
Explicit `--mode dev` permits uncommitted development work and keeps the `-dev`
filename and development notices. Both modes require aligned versions and a
passing native protocol check; each archive includes `QUALIFICATION.json`.

The shared publish workflow builds Windows x64 native ZIP and MCPB assets with
Python 3.12.10 and PyInstaller 6.21.0. A failed native build blocks PyPI publication
and asset attachment. The workflow checks native and source-plugin checksums
before attaching both sets to the same release, without replacing existing
assets. The source plugin remains separate; its MCPB requires installed Python.

Local development builds stay unpublished, even when their embedded version
matches an existing release. This candidate awaits its first workflow run.
Clean-device and supported-client acceptance and signing decisions are separate
release steps. Deterministic archives give a stable zip layout; whether the
compiler output repeats across machines and builds is untested.

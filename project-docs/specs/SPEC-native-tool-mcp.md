# Native Flywheel tool package

The approved requirement is a local MCPB companion to the full Flywheel client,
using the same frozen engine bytes and release version. It requires no installed
Python, model or publisher compute. The user selects separate workspace and state
directories; the package supplies no write, execution or network grants.

The existing `--mcp` includes model and Canon calls outside its run grants.
The new `--tool-mcp` profile exposes only public skill resources, local identity
and read-only receipt inclusion verification. All other tools and methods refuse.
Normal `--mcp` behavior stays unchanged. This is a restricted companion surface,
not a claim that every full-client function works inside another host.

Implementation plan: add strict profile and argument dispatch; include the two
public resource files in the freeze; build a deterministic binary MCPB from the
exact installer engine stage; bind payload paths/hashes to PyInstaller's collection
record; require clean exact version-tag source by default, explicit `--dev` for
development; qualify the actual frozen protocol using synthetic receipts and the
existing Windows Job runner; attach the companion and checksum to the existing
candidate and explicit protected publishing workflows.

Validation includes hostile environment grants, denied model/context/exec calls,
path escapes, links, missing resources and altered payloads. Source and runtime
tests do not prove clean-machine installation or marketplace acceptance. An actual
old-binary resource call failed with the missing SKILL.md before the data fix.

Status: implementation in progress. No publication or installed-client mutation.

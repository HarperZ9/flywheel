# Flywheel local evidence companion

The native MCPB adds public evidence-task resources and receipt membership checks
to a compatible local client. It uses the same frozen engine payload as the
Windows Flywheel installer, with its Python runtime included. Flywheel remains
the full client; this companion exposes a restricted set of local tools.

Select two existing, separate local directories when the client asks: a workspace
and receipt state containing an `envelopes` folder. The companion reads receipt
envelope hashes in the selected state and returns replayable membership proofs.
It does not create either directory. A missing envelope folder is an empty log.
Membership does not establish that the receipt is true or complete.

The `--tool-mcp` profile exposes `flywheel.tool_status`,
`receipt.verify_inclusion`, and the two public evidence-task resources. It does
not expose model calls, endpoint probes, Canon subprocesses, file writes or
command execution. Inherited model credentials or grant settings do not expand
this profile. The user's client still controls whether submitted text reaches
its own model. No publisher-hosted service or publisher-funded compute is used.

## Packaging and checks

The native archive is built beside the installer on the same release workflow.
Its version follows the full client version. The [source tools plugin](source-tool-plugin.md)
uses that same version and requires an installed Python runtime. The separate
evidence-task skill keeps its own compatibility version. The builder compares every engine file against both
the installer staging directory and PyInstaller's collection record, and rejects
unexpected files, links, private state paths and changed bytes. An accepted
checksum is required before the protected publishing workflow attaches the MCPB.

```text
python scripts/build_native_mcp_bundle.py --engine ENGINE --installer-engine INSTALLER_ENGINE --collect-toc COLLECT_TOC --out OUTPUT
python scripts/check_frozen_tool_mcp.py --executable ENGINE/flywheel-gateway.exe --expected-version VERSION --receipt RECEIPT
```

Release mode requires a clean checkout at the exact version tag. Local work must
pass `--dev`; the resulting name and manifest identify development bytes. Do not
publish a development archive. The archive includes source/runtime notices from
the installer payload. Installed-client, clean-device and marketplace acceptance
remain separate checks. A protocol test on the build machine does not prove them.

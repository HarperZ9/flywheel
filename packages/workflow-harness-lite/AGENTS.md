# AGENTS.md -- Workflow Harness Lite

## Project Boundary

Workflow Harness Lite is a dependency-free Node CLI and library for bounded
local command workflows. It runs explicitly configured local commands, redacts
output previews, and can emit compact Telos bounded-run receipts.

## Public Delivery Rules

- Keep `README.md`, `USAGE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AUTHORS.md`,
  `LICENSE`, `.github/FUNDING.yml`, CI workflows, examples, and brand assets
  present.
- Do not commit generated reports, local receipts, private configs, credentials,
  or raw command output from real workspaces.
- Public examples must stay synthetic and bounded.
- Receipt outputs must not include raw commands, raw stdout, raw stderr, or
  private payloads.

## Developer Verification

Run the native package gate before publishing:

```sh
npm test
npm pack --dry-run
```

For receipt changes, add tests that assert raw command/output material stays out
of the Telos receipt.

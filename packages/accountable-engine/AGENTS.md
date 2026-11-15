# AGENTS.md -- Accountable Engine

## Project Boundary

Accountable Engine is a public coordination pattern and PowerShell tool for
evidence-first human/agent work. It records claims, decisions, and receipts; it
does not make authorization decisions, deploy software, or perform external
side effects beyond local file writes requested by the operator.

## Public Delivery Rules

- Keep `README.md`, `USAGE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AUTHORS.md`,
  `LICENSE`, `.github/FUNDING.yml`, `.github/workflows/ci.yml`,
  `STATE.template.md`, and `critic.ps1` aligned.
- Public claims must point to repository files, commands, commits, or receipts.
- Do not commit `.env` files, private client state, generated decision logs,
  local transcripts, credentials, or private corpus material.
- Keep language explicit for public readers: explain what the tool does, who it
  helps, and how a developer verifies it locally.

## Developer Verification

Use Windows PowerShell for the local gate:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\critic.ps1
git status --short
```

When changing `critic.ps1`, also update `USAGE.md`, `STATE.template.md`, and the
CI workflow if the command contract changes.

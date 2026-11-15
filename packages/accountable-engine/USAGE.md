# Accountable Engine Usage

## What It Is

Accountable Engine is a small, local accountability layer for AI-assisted
engineering work. It gives a repository a state template and a critic script so
humans and agents can track claims, evidence, decisions, and unfinished work
without relying on chat memory.

## Install

Clone the repository:

```powershell
git clone https://github.com/HarperZ9/accountable-engine.git
cd accountable-engine
```

No package install is required. The reference tool is `critic.ps1`.

## Start A Ledger

Copy the state template into the working ledger for your project:

```powershell
Copy-Item .\STATE.template.md .\STATE.md
```

Fill in one claim at a time. Each claim should name the work, the branch, the
evidence required to close it, and the final receipt.

## Run The Critic

Use Windows PowerShell locally:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\critic.ps1
```

The critic reads `STATE.md` when present, checks local git subdirectories, and
prints questions about unfinished branches, focus, verification, and scope.

## Record A Decision

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\critic.ps1 -For VERIFY -Record "Run tests before claiming the import path is fixed."
```

This appends a decision receipt to `DECISIONS.md`. Treat generated local decision
logs as project artifacts; review them before committing in another repository.

## Verify This Repository

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\critic.ps1
git status --short
```

The command should exit successfully and print the standup sections:
`FINISH`, `FOCUS`, `VERIFY`, and `SCOPE`.

## Boundary

- The tool reads local files and git metadata.
- `-Record` appends a local `DECISIONS.md` file.
- The tool does not deploy, publish, call external services, or grant authority.
- Do not use it to store secrets, credentials, private client records, or raw
  transcript bodies.

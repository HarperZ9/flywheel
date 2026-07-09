# Workspace Context Map

Date: 2026-07-09

Status type: current local context map, not a full workspace index.

## Observed roots

Primary harness root:

- `C:\dev\local-model`

Related tool roots observed during targeted checks:

- `C:\dev\aleph`
- `C:\dev\public\crucible`
- `C:\dev\public\forum`
- `C:\dev\public\gather`
- `C:\dev\public\index`
- `C:\dev\public\mneme`
- `C:\dev\public\plexus`
- `C:\dev\public\relay`
- `C:\dev\public\telos`
- `C:\dev\public\pubscan`
- `C:\dev\tools`

Runtime and harness-adjacent roots observed:

- `E:\local-model-run`
- `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop`
- `C:\tmp`

## Context lanes

| Lane | Current source | Current evidence status | Next gate |
| --- | --- | --- | --- |
| Harness code | `C:\dev\local-model` | Active local working tree. | Dry-plan and focused seed execution. |
| Tool corpus | `C:\dev`, `C:\dev\public`, `C:\dev\tools` | Key roots observed. | Run context inventory and tool readiness receipts. |
| Local models | `E:\local-model-run` | Root exists. | Endpoint profile, endpoint gate, model file inventory, checksums. |
| OpenCode | `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop` | Root exists. | Adapter/config proof and benchmark run artifact. |
| Scratch/temp artifacts | `C:\tmp` plus configured artifact roots | Root exists; prior benchmark-like artifacts are referenced by harness docs. | Run context inventory with artifact-root scan. |
| Index context | `C:\dev\public\index` | MCP context envelope currently fails with `Transport closed`. | Stabilize MCP transport or run fallback receipt. |

## Boundaries

This map intentionally avoids claiming that every repository has been deeply scanned. It records the context roots already observed and the next command gates needed to convert root presence into evidence.


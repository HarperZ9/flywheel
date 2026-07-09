# External documentation sync

External documentation should mirror the current internal package state without exposing secrets, unpublished weights, private corpora, local caches, or authenticated session details.

## Public source set

- `project-docs/HARNESS-PACKAGING.md`
- `project-docs/flagship/README.md`
- `project-docs/flagship/DEMOS.md`
- `project-docs/flagship/WALKTHROUGH.md`
- `project-docs/releases/14B/`
- `project-docs/releases/32B/`
- `artifacts/exe/harness_architecture_report.local.md`
- `artifacts/exe/tool_operator_guide.local.md`
- `artifacts/exe/huggingface_release_stage.local.md`

## Redaction policy

- Include package paths, schemas, commands, repo IDs, and non-secret local endpoint defaults.
- Exclude `.env` files, tokens, API keys, private keys, model weights, caches, raw private corpora, and authenticated account state.
- Summarize benchmark outcomes only after benchmark artifacts are finalized and approved for publication.

## Sync procedure

1. Rebuild the package.
2. Confirm package doctor is `SHIP_READY`.
3. Copy the public source set into the external documentation repository or site.
4. Replace local absolute paths with repo-relative or user-facing paths where appropriate.
5. Confirm model upload status remains gated unless the Hugging Face staging receipt says `READY_TO_UPLOAD`.
6. Publish external docs only after operator approval.

# Frozen receipt transport parity

Status: wired into the frozen gateway checker; actual Windows executable acceptance
passed on 2026-09-15. This is a development candidate check, not release acceptance.

The installed engine must expose its receipt operation over local MCP as well as
HTTP. A source-only CLI test cannot establish that PyInstaller includes the same
operation or that the executable dispatches to it.

The frozen gateway checker will create two synthetic envelope files inside its
new isolated profile. Against the actual binary, it will initialize MCP, discover
`receipt.verify_inclusion`, request one known leaf, request one absent leaf, and
submit malformed input. The MCP proof must exactly equal the actual HTTP proof
for the same configured root and run root. Text and structured output must agree.
Neither adapter may promote missing evidence to inclusion. The child must exit
cleanly after stdin EOF, without ambient credentials or provider calls.

The stdio child starts suspended and enters the existing Windows Job before
execution. The checker supplies EOF through an owned input file, monitors output
size, rejects stderr and nonzero exit, and requires all Job descendants to be
terminal before reporting success. Timeout and oversized-output cases exercise
termination controls. The checker does not infer process cleanup from parent exit.

Negative controls reject a different HTTP proof, disagreement between structured
and text output, absent leaves represented as included, and malformed requests
reported as success. Error receipts use fixed codes and omit raw child output.

This verifies transport parity and packaging of a bounded read-only operation.
It does not establish receipt semantics, evidence completeness, checkpoint identity,
remote MCP interoperability, model-backed execution or release readiness.

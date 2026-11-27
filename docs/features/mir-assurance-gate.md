# MIR Assurance Gate

The MIR assurance gate audits all four compile time safety sweeps emitted by the BuildLang compiler. Every check fails closed. It verifies capability effect confinement, worst case execution time and RV64 stack frame ceilings, constant time secret taint freedom, and bit exact floating point determinism before downstream publication proceeds.

Each pillar manifest passes through strict schema and primitive guards that reject malformed JSON, non boolean flags, invalid commit digests, and mismatched aggregate counts. The effect check requires zero egress isolation across every core module and blocks any reference to denied filesystem, network, process execution, or unsafe effects. Stack verification enforces recursion freedom alongside single frame ceilings under two thousand forty eight bytes and transitive page budgets under four thousand ninety six bytes.

Constant time and determinism sweeps must report zero violations. Every audited module must achieve full deterministic coverage and confirm all planted negative controls. A cross pillar consistency check verifies that all four sweeps inspected the exact same deduplicated module set and total function count, preventing stitched or partial manifests from slipping past review.

Run the command line tool with all four JSON manifests to receive a structured JSON verdict. It exits zero on a complete pass and two on any rejection. Because the verifier uses only the Python standard library under the MIT license, third party auditors can replay compiler safety checks completely offline.

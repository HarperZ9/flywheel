# Threshold Storage Attestation Gate

The threshold storage attestation gate verifies Slice 36 Zero C Shamir Threshold HSM receipts alongside Slice 37 Zero C Reed Solomon self healing RAID 6 filesystem receipts. Every check fails closed. It audits all five compiled target binaries, their RFC 6962 cryptographic audit roots, and fail closed attack rejection totals without third party dependencies.

For each canonical receipt, the parser enforces schema integrity, MATCH verdict status, zero oracle exit code, BuildLang engine attribution, and valid SHA256 digest envelopes. Both slices must present the complete five ISA binary matrix covering Windows x64 PE, Linux x64 ELF, RISC V 64 ELF, AArch64 ELF, and WebAssembly alongside the originating BuildLang source file.

Domain checks confirm three of five Shamir threshold parameters for the virtual HSM, four data plus two parity shards covering all fifteen single and double erasure patterns for the RAID 6 filesystem, at least twenty five verified zero C binaries, and distinct 64 hex RFC 6962 audit roots. Optional disk verification inspects every compiled binary directly for raw PE, ELF, or WebAssembly magic headers, exact byte lengths, and matching SHA256 digests while rejecting path traversal.

Invoke the command line tool with both receipt files to emit a structured JSON verdict. It exits zero when every invariant passes and two on any tampering or missing binary. Because the verifier relies strictly on the Python standard library under the MIT license, offline auditors can replay full storage and HSM security checks deterministically.

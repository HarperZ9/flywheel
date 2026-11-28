# GPU Shader 520 Gate

The GPU shader 520 gate verifies the Quingentennial five hundred twenty certified five backend GPU compute shader pack alongside the RLVR v14 dataset manifest and Paper 8 release metadata. Every invariant fails closed. Downstream pipelines can audit shader coverage, superoptimizer rewrite accounting, dataset balance, and staged publication hygiene offline in one command.

Shader verification parses both the cumulative 520 shader manifest and the Wave 163A validation report. It enforces MIT licensing, exact cardinality of one hundred four unique kernels across WGSL, HLSL, Metal, SPIR V, and GLSL, zero duplicate pairs, passing certificate status on every shader, exact byte and rewrite totals, full external validator coverage across dxc, glslang, spirv val, and naga, and all three planted fail closed controls.

Dataset and publication checks validate the RLVR v14 manifest and Paper 8 Octet metadata in the same pass. The RLVR verifier confirms MIT licensing, disabled hub pushes, exactly one thousand two hundred eighty tasks split cleanly across train and eval sets, thirty six categories with at least sixty four planted negative traps, and valid SHA256 pins. The Paper 8 verifier enforces CC BY 4.0 licensing, MIT code licensing, a valid ORCID identifier, local staging without external uploads, and exact six page PNG coverage.

Run the command line tool with all four JSON manifests to produce a deterministic JSON verdict. It exits zero on full verification and two whenever any metric, digest, or control drifts. Pure standard library packaging under the MIT license ensures zero external runtime dependencies for reproducible release auditing.

# GPU 400-Pack and RLVR v12 Certification Gate

`harness/gpu_400pack_gate/` is a pure-stdlib MIT verifier for the Quadricentennial 400-shader five-backend GPU compute suite and the `JFC3P-14B-Oracle-v12` 1,024-task RLVR dataset manifest.

## Checks Performed

The verifier inspects every shader entry across all 80 unique MIT compute kernels and five GPU backends: `wgsl`, `hlsl`, `msl`, `spirv`, and `glsl`. It rejects duplicate kernel-target pairs, missing backends, uncertified shaders, invalid 64-character `SHA-256` hashes, non-MIT licenses, and cumulative Superopt V6 rewrite totals below `2,817`.

When an RLVR v12 manifest is supplied, the gate verifies pure `MIT` licensing, `1,024` total tasks split cleanly across `880` train and `144` eval entries, `28` category counts summing exactly to `1,024`, valid artifact `SHA-256` digests, and optional on-disk file hash verification.

## Scope Limits

This gate verifies shader manifests, certificate hashes, and dataset manifests. It does not invoke GPU compilers or train language models.

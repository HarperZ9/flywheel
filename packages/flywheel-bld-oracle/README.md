# Flywheel BuildLang Oracle Core

The Flywheel BuildLang oracle core packages the deterministic verdict engine, FNV 1a receipt and Merkle accumulator, and tolerance and control gap validator in pure BuildLang compiled directly to standalone WebAssembly. Every check fails closed. Any runtime supporting WebAssembly can replay verdict logic with zero external dependencies.

The compiled module exports pure numeric functions with no host imports. Callers accumulate leaf words with FNV 1a, fold pairs through domain separated Merkle nodes, verify expected digests, validate numerical tolerance ceilings and minimum control gaps, and compute final verdict codes. Missing planted controls return minus one hundred one, passing planted controls return minus one hundred two, and tampered receipts return minus one hundred three.

Verification runs across both Node and Python using the bundled test suites. Known answer vectors check exact bit level parity between WebAssembly execution and reference arithmetic while four planted negative controls confirm fail closed rejection on every violation class.

# Renderer Parity Gate

## Overview

`harness/renderer_parity_gate` verifies `native/bld/` C++23 to BuildLang 0-ULP renderer parity ledgers in pure Python stdlib under the OSI MIT license. Every row is checked for valid module numbering, unique `.bld` names, non-zero 64-bit FNV-1a hex pins, strict `0`-ULP error bounds, and planted perturbation rejection flags.

## Attestation and Fail-Closed Rules

Calling `verify_renderer_parity` or `verify_renderer_parity_files` returns an immutable `RendererParityReport`. The report exposes the boolean `passed` verdict, module count and range, exact zero-ULP count, planted controls caught, index SHA-256 digest, deterministic `renderer_parity_attestation_sha256`, and explicit violations. Any tampered FNV-1a pin, missing module in the expected sequence, non-zero ULP error, forged catalogue ID, or `NaN`/`Inf`/`bool` numeric parameter triggers immediate fail-closed rejection.

## Scope Limits

This oracle checks parity index schema, 64-bit FNV-1a pin matching, planted control flags, and caller-supplied catalogue or receipt verdicts in pure Python stdlib. It does not compile C++23 or BuildLang sources or launch GPU renderers.

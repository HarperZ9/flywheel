"""harness.infra -- infrastructure-layer controls for the agentic security gap.

Bridges the 11 gap artifacts from the ARCHIVE QUERY 2144 (July 2026 Agentic
Security Convergence) that Flywheel's agent-layer accountability engine did
not cover. Each module emits sealed, chain-linked receipts that compose with
the existing tool-call receipt chain and the organizational learning loop.

Modules:
  trust_model       -- Artifact 16: System Architecture and Trust Model
  acquisition       -- Artifact 12: Archive Acquisition Manifest
  egress            -- Artifact 17: Data-Flow and Egress Control Matrix
  egress_matrix     -- the allowlist matrix for egress
  reality_contract  -- Artifact 20: Target Allowlist and Reality Contract
  credential_scanner-- Artifact 22: Credential and Secret Exposure Register
  isolation_test    -- Artifact 21: Isolation Acceptance Test
  kill_switch       -- Artifact 26: Stop Conditions and Kill Authority
  correlator        -- Artifact 24: Continuous Monitoring Specification
  incident_sheet    -- Artifact 14: Incident Identity Sheet
  run_bom           -- Artifact 18: Model/Tool/Permission BOM
  partner_assurance -- Artifact 23: Third-Party Evaluation Assurance Package

Standard library only unless psutil or native bindings are available.
"""

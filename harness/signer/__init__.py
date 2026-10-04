"""signer -- a record signer that runs under a different identity from the agent.

Every pre-action record used to be sealed with an unkeyed sha256, by code that
runs as the agent's own OS user. A writer who recomputes the whole chain passes
that check, so the store was evidence against accidents and not against the
agent. This package moves the pen out of the agent's reach:

  * ``server`` runs as a separate OS user (Linux) or a separate Windows account,
    owns an Ed25519 key the agent cannot read, and answers on a narrow local
    socket or named pipe. It signs one statement type only, a record
    attestation, and it refuses to sign a sequence number twice, so history it
    has signed cannot be rewritten through it.
  * ``client`` is what the agent-side store calls. It never sees the key.
  * ``statement`` builds and checks attestations with the stdlib verifier, so
    a stranger needs no dependencies to check a store.

The signer measures the caller's identity from the kernel (``SO_PEERCRED`` on
Linux, the pipe client token on Windows) and writes the result into every
signed statement as ``isolation``. A signer that shares the agent's identity
still works, and every record it signs says ``same-identity``.

Setup and limits: docs/SEPARATE-SIGNER.md.
"""

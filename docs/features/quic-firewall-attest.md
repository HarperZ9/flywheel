# QUIC Firewall Attestation Gate

`harness/quic_firewall_attest/` is a pure-stdlib MIT verifier for Slice 31 Zero-C five-ISA QUIC-Lite encrypted transport and deny-by-default `CAP_NET_PEER` firewall receipts.

## Checks Performed

The verifier simulates the 64-bit sliding anti-replay window across observed packet numbers and checks final `max_pn` and `bmp_lo` state. Any duplicate packet number or window underflow fails closed immediately.

For policy enforcement, the gate requires `firewall_default == "DENY"` and confirms every allow rule carries `CAP_NET_PEER` with an explicit non-wildcard peer identifier. It also verifies all five target architecture binaries with valid 64-character `SHA-256` digests, optional on-disk hash checks, and all four network attack vectors, `replay_packet`, `unapproved_peer_egress`, `aead_tag_tamper`, and `pn_window_underflow`, failing closed across all five ISAs.

## Scope Limits

This module checks receipt structure, anti-replay bitmaps, firewall policy declarations, binary digests, and planted rejection controls. It does not open sockets or inspect live packet captures.

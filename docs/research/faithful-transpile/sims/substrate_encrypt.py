"""Substrate 4 — encryption: LOSSLESS in bits, yet the criterion is inaccessible without the key.

This is the sharpest test of the author's black-hole intuition: information is not erased, it is
SCRAMBLED — fully preserved (a bijective cipher, zero bit-loss) but unreadable for a criterion unless
you hold the external key. It forces a refinement of the principle: faithfulness can fail two ways —
  CONCEALMENT : phi factors through T composed with an EXTERNAL secret (decrypt-with-key) — recoverable.
  DESTRUCTION : phi cannot factor through T at all (bits that determine phi are gone) — unrecoverable.
Both demand an external criterion; only concealment is reversible. "Energy not lost, transformed beyond
perception" = concealment, made exact.

Plaintext = D bytes. Criterion phi(x) = (mean byte > 128)  [a content property].
Transforms:
  encrypt   : XOR each byte with a keystream from a key — bijective, LOSSLESS (0 bit-loss).
  low_nibble: keep only the low 4 bits of each byte — LOSSY, and it discards exactly the high bits
              that determine phi (mean>128), so phi is DESTROYED, not merely concealed.
Witness = the external key (for encrypt) / nothing can help (for low_nibble).

Stdlib only, deterministic.
"""
from __future__ import annotations
import random

D, N = 32, 4000


def phi(x):
    return (sum(x) / len(x)) > 128.0


def keystream(key, idx, n):
    # FRESH per-message keystream (key + per-message nonce idx) — a proper stream cipher, not a
    # reused-keystream two-time pad. XOR with a uniform keystream makes each ciphertext byte uniform.
    r = random.Random(f"{key}:{idx}")
    return [r.randrange(256) for _ in range(n)]


def encrypt(x, key, idx):
    return [b ^ k for b, k in zip(x, keystream(key, idx, len(x)))]


def decrypt(c, key, idx):
    return encrypt(c, key, idx)       # XOR is its own inverse (needs key AND the nonce idx)


def low_nibble(x):
    return [b & 0x0F for b in x]


def predict_phi_from_bytes(rep):
    """Best within-substrate guess at phi using the rep's OWN mean (no external key/criterion)."""
    return (sum(rep) / len(rep)) > 128.0


def main():
    rng = random.Random(7)
    KEY = 20260623
    # balanced dataset: half with mean>128, half below
    X = []
    for _ in range(N):
        hi = rng.random() < 0.5
        base = rng.randint(150, 230) if hi else rng.randint(20, 110)
        X.append([max(0, min(255, base + rng.randint(-20, 20))) for _ in range(D)])

    cipher = [encrypt(x, KEY, i) for i, x in enumerate(X)]
    nibble = [low_nibble(x) for x in X]

    def acc(reps, recover):
        ok = sum(1 for x, r in zip(X, reps) if recover(r) == phi(x))
        return ok / len(X)

    # phi read from the rep ALONE (no key):
    acc_cipher_nokey = acc(cipher, predict_phi_from_bytes)
    acc_nibble_nokey = acc(nibble, predict_phi_from_bytes)
    # phi read WITH the external witness:
    acc_cipher_key = sum(1 for i, x in enumerate(X)
                         if phi(decrypt(cipher[i], KEY, i)) == phi(x)) / len(X)  # decrypt then read
    acc_nibble_key = acc(nibble, lambda r: phi(r))                 # no key exists; best effort on the rep
    # internal statistic (entropy proxy: mean + spread) — does it betray phi?
    def meanspread(reps):
        ms = [sum(r) / len(r) for r in reps]
        return sum(ms) / len(ms)
    int_cipher = meanspread(cipher)

    print(f"plaintext {D} bytes; phi = (mean byte > 128). N={N}\n")
    print("transform    bit-loss   phi-acc (rep alone)   phi-acc (with external witness)")
    print(f"  encrypt      0.00       {acc_cipher_nokey:.3f}  (~chance)         {acc_cipher_key:.3f}  (key recovers)")
    print(f"  low_nibble   0.50       {acc_nibble_nokey:.3f}                  {acc_nibble_key:.3f}  (no key helps — destroyed)")
    print(f"\n  ciphertext internal mean-of-means = {int_cipher:.1f} (~127.5 regardless of phi -> blind)")

    print("\n--- verdict (substrate 4: encryption / reversible scrambling) ---")
    p_conceal = abs(acc_cipher_nokey - 0.5) < 0.05 and acc_cipher_key > 0.98
    p_destroy = acc_nibble_key < 0.85
    p_blind = abs(int_cipher - 127.5) < 6
    print(f"(refine) CONCEALMENT: encrypt is 0 bit-loss, phi unreadable alone ({acc_cipher_nokey:.3f}) "
          f"but the external key fully recovers it ({acc_cipher_key:.3f})  -> {'HOLDS' if p_conceal else 'FALLS'}")
    print(f"(refine) DESTRUCTION: low_nibble drops phi's bits; even full access can't recover "
          f"({acc_nibble_key:.3f} < 0.85)  -> {'HOLDS' if p_destroy else 'FALLS'}")
    print(f"(2) internal blindness: ciphertext stats ~uniform regardless of phi  -> {'HOLDS' if p_blind else 'FALLS'}")
    print("\nSTICKS" if (p_conceal and p_destroy and p_blind) else "\nFALLS",
          "— substrate 4: 'loss' splits into concealment (reversible) vs destruction; the witness is external in both.")


if __name__ == "__main__":
    main()

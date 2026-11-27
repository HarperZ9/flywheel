"""Renewal roots signed by a quorum of seats (SPEC.md section 7).

Once per epoch the seats build a Merkle root with one blinded leaf per
device in good standing. The blind comes from the device's previous
heartbeat fingerprint, which both the seats and the device know, so the
public sees a count and cannot link a device across epochs.
"""

from __future__ import annotations

import hashlib

from .crypto import envelope
from .merkle import MerkleTree, leaf_hash, verify_inclusion


def blind(prev_heartbeat_fp: str, epoch: int) -> str:
    return hashlib.sha256(f"fsp/v0/blind\n{prev_heartbeat_fp}\n{epoch}".encode()).hexdigest()


def renewal_leaf(device_key: str, epoch: int, blind_hex: str) -> bytes:
    return hashlib.sha256(f"fsp/v0/renewal-leaf\n{device_key}\n{epoch}\n{blind_hex}".encode()
                          ).digest()


def build_root(members: dict[str, str], epoch: int) -> tuple[MerkleTree, list[str]]:
    """members maps device key to the heartbeat fingerprint used for its blind."""
    order = sorted(members)
    tree = MerkleTree()
    for key in order:
        tree.append(renewal_leaf(key, epoch, blind(members[key], epoch)))
    return tree, order


def renewal_body(tree: MerkleTree, epoch: int, valid_from_ms: int, validity_s: int,
                 criterion_id: str) -> dict:
    return {"epoch": epoch, "root": tree.root().hex(), "leaf_count": len(tree.leaves),
            "valid_from_ms": valid_from_ms, "valid_until_ms": valid_from_ms + validity_s * 1000,
            "criterion_id": criterion_id}


def sign_renewal(body: dict, seats: list) -> dict:
    return envelope("renewal", body, [s.signer for s in seats])


def leaf_package(tree: MerkleTree, order: list[str], members: dict[str, str],
                 device_key: str) -> dict | None:
    if device_key not in members:
        return None
    index = order.index(device_key)
    size = len(order)
    return {"index": index, "size": size, "hb_fp": members[device_key],
            "path": [h.hex() for h in tree.inclusion_proof(index, size)]}


def leaf_valid(renewal: dict, device_key: str, pkg: dict, own_fps: list[str]) -> bool:
    """The device's own check: its blinded leaf is in the signed root."""
    body = renewal["body"]
    if pkg["hb_fp"] not in own_fps or pkg["size"] != body["leaf_count"]:
        return False
    data = renewal_leaf(device_key, body["epoch"], blind(pkg["hb_fp"], body["epoch"]))
    path = [bytes.fromhex(h) for h in pkg["path"]]
    return verify_inclusion(leaf_hash(data), pkg["index"], pkg["size"], path,
                            bytes.fromhex(body["root"]))


def refusal(seat, renewal_fp: str, criterion_id: str, disputed: list[str]) -> dict:
    body = {"subject_fp": renewal_fp, "criterion_id": criterion_id,
            "disputed_leaves": disputed, "seat": seat.key}
    return envelope("renewal-refusal", body, [seat.signer])

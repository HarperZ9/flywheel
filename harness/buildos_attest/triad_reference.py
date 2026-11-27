# SPDX-License-Identifier: MIT
"""Independent pure-stdlib reference for the Slice 20 BuildOS Microkernel Triad.

Re-derives the signed-boot RFC 6962 log root, the W^X capability scheduler
dispatch-trace SHA-256, and the zero-copy IPC Merkle VFS inode root from first
principles using 0x00 leaf / 0x01 node domain separation.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Re-derives the published Slice 20 triad reference digests (kernel image "
    "SHA-256, RFC 6962 boot log root, 9-tick scheduler trace SHA-256, and "
    "4-block VFS inode root) in pure Python. Does not execute BuildOS binaries "
    "or emulate any instruction set."
)

KERNEL_IMAGE = b"BUILDOS-CORE-SLICE20-UNIFIED-TRIAD-SLOTB-KERNEL-2026-11-27-OK!\x00\x00"
BOOT_EPOCH = 20
BOOT_SLOT = 2
MANIFEST_MAGIC = 0x424C4F53
SCHED_TRACE: tuple[int, ...] = (0, 1, 0, 1, 2, 2, 2, 3, 3)
SCHED_TICKS = 9
VFS_BLOCK_COUNT = 4
VFS_BLOCKS: tuple[bytes, ...] = (
    b"TRIAD-VFS-BLK0-SUPERBLOCK-SLICE20-CONTENT-ADDRESSED-OK!!!!!!\x00\x00\x00\x00",
    b"TRIAD-VFS-BLK1-INODE-META-SLICE20-LINEAR-OWNERSHIP-IPC-OK!!!\x00\x00\x00\x00",
    b"TRIAD-VFS-BLK2-SCHED-LOG--SLICE20-DETERMINISTIC-TRACE-OK!!!!\x00\x00\x00\x00",
    b"TRIAD-VFS-BLK3-RECEIPT-DB-SLICE20-ZERO-C-FIVE-ISA-TRIAD-OK!!\x00\x00\x00\x00",
)


@dataclass(frozen=True)
class TriadReference:
    """Independently re-derived Slice 20 triad reference digests."""

    img_sha256_hex: str
    boot_log_root_hex: str
    sched_trace_sha_hex: str
    vfs_inode_root_hex: str

    def to_dict(self) -> dict[str, str]:
        """Serialize reference digests into a JSON-compatible dictionary."""
        return {
            "img_sha256_hex": self.img_sha256_hex,
            "boot_log_root_hex": self.boot_log_root_hex,
            "sched_trace_sha_hex": self.sched_trace_sha_hex,
            "vfs_inode_root_hex": self.vfs_inode_root_hex,
        }


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaf_hash(digest: bytes) -> bytes:
    """RFC 6962 leaf hash over an already-hashed 32-byte payload digest."""
    return _sha256(b"\x00" + digest)


def node_hash(left: bytes, right: bytes) -> bytes:
    """RFC 6962 interior node hash with 0x01 domain separation."""
    return _sha256(b"\x01" + left + right)


def merkle_root_of_four(leaf_digests: Sequence[bytes]) -> bytes:
    """Compute a balanced 4-leaf RFC 6962 root from four leaf hashes."""
    if len(leaf_digests) != 4 or any(len(d) != 32 for d in leaf_digests):
        raise ValueError("exactly four 32-byte leaf hashes are required")
    left = node_hash(leaf_digests[0], leaf_digests[1])
    right = node_hash(leaf_digests[2], leaf_digests[3])
    return node_hash(left, right)


def derive_boot_log_root(kernel_image: bytes = KERNEL_IMAGE, epoch: int = BOOT_EPOCH) -> tuple[bytes, bytes]:
    """Return (kernel image SHA-256, RFC 6962 signed-boot log root)."""
    img_sha = _sha256(kernel_image)
    manifest = img_sha + struct.pack(">IIII", epoch, BOOT_SLOT, len(kernel_image), MANIFEST_MAGIC)
    leaves = (
        leaf_hash(_sha256(b"TRIAD-BOOT-LOG-LEAF0-E19")),
        leaf_hash(_sha256(manifest)),
        leaf_hash(_sha256(b"TRIAD-BOOT-LOG-LEAF2-AUD")),
        leaf_hash(_sha256(b"TRIAD-BOOT-LOG-LEAF3-AUD")),
    )
    return img_sha, merkle_root_of_four(leaves)


def derive_sched_trace_sha(trace: Sequence[int] = SCHED_TRACE) -> bytes:
    """Return SHA-256 over the 9-tick W^X capability dispatch trace record."""
    if len(trace) != SCHED_TICKS:
        raise ValueError(f"trace must contain exactly {SCHED_TICKS} ticks")
    record = list(trace) + [SCHED_TICKS, VFS_BLOCK_COUNT, BOOT_EPOCH]
    return _sha256(struct.pack(">12I", *record))


def derive_vfs_inode_root(blocks: Sequence[bytes] = VFS_BLOCKS) -> bytes:
    """Return the content-addressed RFC 6962 VFS inode root over four blocks."""
    return merkle_root_of_four([leaf_hash(_sha256(b)) for b in blocks])


def derive_triad_reference() -> TriadReference:
    """Derive the full Slice 20 triad reference from first principles."""
    img_sha, boot_root = derive_boot_log_root()
    return TriadReference(
        img_sha256_hex=img_sha.hex(),
        boot_log_root_hex=boot_root.hex(),
        sched_trace_sha_hex=derive_sched_trace_sha().hex(),
        vfs_inode_root_hex=derive_vfs_inode_root().hex(),
    )

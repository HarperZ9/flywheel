// receipt_proof.dart -- the client side of flywheel.receipts-proof/v2.
//
// The gateway serves {schema, leaf, index, tree_size, merkle_root,
// audit_path}; this model parses it defensively and recomputes the
// Merkle inclusion in pure Dart. MATCH only ever leaves this file when
// the recomputed root equals the advertised one; anything malformed is
// UNVERIFIABLE, never a pass. Vectors are shared with
// tests/test_receipt_proof_route.py.
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

const String kReceiptProofSchema = 'flywheel.receipts-proof/v2';

/// One audit-path step exactly as served: an opaque `side` string so a
/// tampered or unknown side survives parsing only to be rejected by the
/// verifier, never silently normalized into a valid direction.
class ReceiptProofStep {
  final String hash;
  final String side;
  const ReceiptProofStep({required this.hash, required this.side});
}

/// The receipts-proof/v2 wire object. [fromJson] degrades to null on any
/// shape mismatch rather than crashing; content validity lives in
/// [verifyReceiptProof].
class ReceiptProof {
  final String schema;
  final String leaf;
  final int index;
  final int treeSize;
  final String merkleRoot;
  final List<ReceiptProofStep> auditPath;
  const ReceiptProof({
    required this.schema,
    required this.leaf,
    required this.index,
    required this.treeSize,
    required this.merkleRoot,
    required this.auditPath,
  });

  static ReceiptProof? fromJson(Map<String, dynamic> j) {
    if (j['schema'] != kReceiptProofSchema) return null;
    final leaf = j['leaf'];
    final root = j['merkle_root'];
    final index = j['index'];
    final size = j['tree_size'];
    final rawPath = j['audit_path'];
    if (leaf is! String || root is! String) return null;
    if (index is! int || size is! int || rawPath is! List) return null;
    final steps = <ReceiptProofStep>[];
    for (final s in rawPath) {
      if (s is! Map<String, dynamic>) return null;
      final h = s['hash'];
      final side = s['side'];
      if (h is! String || side is! String) return null;
      steps.add(ReceiptProofStep(hash: h, side: side));
    }
    return ReceiptProof(
      schema: j['schema'] as String,
      leaf: leaf,
      index: index,
      treeSize: size,
      merkleRoot: root,
      auditPath: steps,
    );
  }
}

enum ReceiptProofVerdict { match, drift, unverifiable }

class ReceiptProofResult {
  final ReceiptProofVerdict verdict;
  final String detail;
  const ReceiptProofResult(this.verdict, this.detail);
}

bool _isHex64(String s) {
  if (s.length != 64) return false;
  for (final c in s.codeUnits) {
    final hex = (c >= 0x30 && c <= 0x39) ||
        (c >= 0x61 && c <= 0x66); // 0-9, a-f
    if (!hex) return false;
  }
  return true;
}

Uint8List _bytesFromHex(String s) {
  if (!_isHex64(s)) return Uint8List(0);
  return Uint8List.fromList([
    for (var i = 0; i < 64; i += 2)
      int.parse(s.substring(i, i + 2), radix: 16)
  ]);
}

Uint8List _hash(int prefix, List<int> a, [List<int>? b]) {
  final out = BytesBuilder()..addByte(prefix)..add(a);
  if (b != null) out.add(b);
  return Uint8List.fromList(sha256.convert(out.toBytes()).bytes);
}

/// Recompute inclusion from the leaf up. Domain separation matches the
/// engine's transparency_log: leaves hash as sha256(0x00 || leaf), nodes
/// as sha256(0x01 || left || right).
ReceiptProofResult verifyReceiptProof(ReceiptProof p) {
  if (p.schema != kReceiptProofSchema) {
    return const ReceiptProofResult(
        ReceiptProofVerdict.unverifiable, 'unsupported proof schema');
  }
  final leafBytes = _bytesFromHex(p.leaf);
  final rootBytes = _bytesFromHex(p.merkleRoot);
  if (leafBytes.isEmpty || rootBytes.isEmpty) {
    return const ReceiptProofResult(
        ReceiptProofVerdict.unverifiable,
        'leaf and merkle root must be 64-hex sha256 digests');
  }
  if (p.treeSize < 1 || p.index < 0 || p.index >= p.treeSize) {
    return const ReceiptProofResult(
        ReceiptProofVerdict.unverifiable, 'index outside the declared tree');
  }
  var cur = _hash(0x00, leafBytes);
  for (final step in p.auditPath) {
    final sib = _bytesFromHex(step.hash);
    if (sib.isEmpty) {
      return const ReceiptProofResult(ReceiptProofVerdict.unverifiable,
          'audit path carries a malformed sibling hash');
    }
    if (step.side == 'left') {
      cur = _hash(0x01, sib, cur);
    } else if (step.side == 'right') {
      cur = _hash(0x01, cur, sib);
    } else {
      return const ReceiptProofResult(ReceiptProofVerdict.unverifiable,
          'audit path carries an unknown side name');
    }
  }
  final computed = cur.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  if (computed == p.merkleRoot) {
    return ReceiptProofResult(ReceiptProofVerdict.match,
        'recomputed on this device from ${p.auditPath.length} sibling hashes');
  }
  return const ReceiptProofResult(ReceiptProofVerdict.drift,
      'the recomputed root does not match the advertised root');
}

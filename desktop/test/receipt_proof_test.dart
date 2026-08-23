// The Dart side of the receipts-proof/v2 contract: the client recomputes
// Merkle inclusion itself and never trusts the server's word for it.
// Vectors are the shared fixtures from tests/test_receipt_proof_route.py;
// MATCH only lands when the recomputed root equals the advertised one.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/receipt_proof.dart';

const _leaves = [
  '0000000000000000000000000000000000000000000000000000000000000001',
  '0000000000000000000000000000000000000000000000000000000000000002',
  '0000000000000000000000000000000000000000000000000000000000000003',
  '0000000000000000000000000000000000000000000000000000000000000004',
  '0000000000000000000000000000000000000000000000000000000000000005',
];
const _root =
    'c48c0df7d9b37592c69ba5ca2afc8ada511550e607e6dfe7fdef6b85d89f5269';
const _proofIdx2 = [
  {
    'hash':
        '82f02cf2ac0074619e6d747c35e08b29431a16943ddf81cfd9065c004ee6364a',
    'side': 'right',
  },
  {
    'hash':
        '0971c8a1ce81287ccbc95aa4f171a5f807fb13ea2118f56b99769459a64906ad',
    'side': 'left',
  },
  {
    'hash':
        '086fb60bd968fe68ecec6a8d826ea5aa7d3d8020e644d7c5d0e07ded456ca3e8',
    'side': 'right',
  },
];

Map<String, dynamic> _v2Doc({
  String? leaf,
  int? index,
  int? treeSize,
  String? merkleRoot,
  List<dynamic>? auditPath,
  String schema = 'flywheel.receipts-proof/v2',
}) =>
    {
      'schema': schema,
      'leaf': leaf ?? _leaves[2],
      'index': index ?? 2,
      'tree_size': treeSize ?? 5,
      'merkle_root': merkleRoot ?? _root,
      'audit_path': auditPath ?? _proofIdx2,
    };

void main() {
  test('parses a strict v2 document defensively', () {
    final p = ReceiptProof.fromJson(_v2Doc());
    expect(p, isNotNull);
    expect(p!.index, 2);
    expect(p.treeSize, 5);
    expect(p.merkleRoot, _root);
    expect(p.auditPath.length, 3);
    expect(p.schema, 'flywheel.receipts-proof/v2');
  });

  test('rejects a wrong-schema or truncated document', () {
    expect(ReceiptProof.fromJson(_v2Doc(schema: 'flywheel.receipts-proof/v1')),
        isNull);
    expect(ReceiptProof.fromJson({'schema': 'flywheel.receipts-proof/v2'}),
        isNull);
  });

  test('the Python vector recomputes to MATCH', () {
    final r = verifyReceiptProof(ReceiptProof.fromJson(_v2Doc())!);
    expect(r.verdict, ReceiptProofVerdict.match);
  });

  test('a single-leaf tree with an empty path verifies', () {
    final r = verifyReceiptProof(ReceiptProof.fromJson(_v2Doc(
            index: 0,
            treeSize: 1,
            leaf: _leaves[0],
            merkleRoot:
                '1fd4247443c9440cb3c48c28851937196bc156032d70a96c98e127ecb347e45f',
            auditPath: []))!);
    expect(r.verdict, ReceiptProofVerdict.match);
  });

  test('odd leaf-count promotion matches the Python walker', () {
    // Index 4 (last of five): its path walks the promoted odd nodes too.
    final doc = _v2Doc(
      leaf: _leaves[4],
      index: 4,
      auditPath: [
        {
          'hash':
              '45f385494f9f6116ec5530e7e9e24e2fdf6388c47d72e29657ce7b860c1484c3',
          'side': 'left',
        },
      ],
    );
    expect(verifyReceiptProof(ReceiptProof.fromJson(doc)!).verdict,
        ReceiptProofVerdict.match);
  });

  test('a flipped sibling side drifts instead of matching', () {
    final flipped = [
      {..._proofIdx2[0], 'side': 'left'},
      _proofIdx2[1],
      _proofIdx2[2],
    ];
    final r = verifyReceiptProof(
        ReceiptProof.fromJson(_v2Doc(auditPath: flipped))!);
    expect(r.verdict, isNot(ReceiptProofVerdict.match));
  });

  test('a reordered path drifts instead of matching', () {
    final reordered = [_proofIdx2[1], _proofIdx2[0], _proofIdx2[2]];
    final r = verifyReceiptProof(
        ReceiptProof.fromJson(_v2Doc(auditPath: reordered))!);
    expect(r.verdict, ReceiptProofVerdict.drift);
  });

  test('an advertised root that disagrees drifts', () {
    final other = '${'f' * 63}0';
    final r = verifyReceiptProof(
        ReceiptProof.fromJson(_v2Doc(merkleRoot: other))!);
    expect(r.verdict, ReceiptProofVerdict.drift);
  });

  test('malformed hex in any step is unverifiable, never a match', () {
    final malformed = [
      {..._proofIdx2[0], 'hash': 'zz${'0' * 62}'},
      _proofIdx2[1],
      _proofIdx2[2],
    ];
    final r = verifyReceiptProof(
        ReceiptProof.fromJson(_v2Doc(auditPath: malformed))!);
    expect(r.verdict, ReceiptProofVerdict.unverifiable);

    final shortHash = [
      {..._proofIdx2[0], 'hash': 'abcd'},
      _proofIdx2[1],
      _proofIdx2[2],
    ];
    expect(
        verifyReceiptProof(
                ReceiptProof.fromJson(_v2Doc(auditPath: shortHash))!)
            .verdict,
        ReceiptProofVerdict.unverifiable);
  });

  test('an unknown side name is unverifiable', () {
    final weirdSide = [
      {..._proofIdx2[0], 'side': 'up'},
      _proofIdx2[1],
      _proofIdx2[2],
    ];
    expect(
        verifyReceiptProof(
                ReceiptProof.fromJson(_v2Doc(auditPath: weirdSide))!)
            .verdict,
        ReceiptProofVerdict.unverifiable);
  });

  test('an out-of-range index is unverifiable before any hashing', () {
    expect(
        verifyReceiptProof(ReceiptProof.fromJson(_v2Doc(index: 9))!).verdict,
        ReceiptProofVerdict.unverifiable);
    expect(
        verifyReceiptProof(ReceiptProof.fromJson(_v2Doc(index: -1))!).verdict,
        ReceiptProofVerdict.unverifiable);
  });

  test('a malformed leaf hex never reaches a match', () {
    expect(
        verifyReceiptProof(
                ReceiptProof.fromJson(_v2Doc(leaf: 'not-hex'))!)
            .verdict,
        ReceiptProofVerdict.unverifiable);
  });
}

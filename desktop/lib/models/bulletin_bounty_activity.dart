final _sha64 = RegExp(r'^sha256:[0-9a-f]{64}$');

String _text(Object? value) => value is String ? value : '';
bool _bool(Object? value) => value is bool && value;
int? _int(Object? value) => value is int ? value : null;
Map<String, Object?> _map(Object? value) =>
    value is Map ? Map<String, Object?>.from(value) : const {};
List<Map<String, Object?>> _maps(Object? value) => value is List
    ? [
        for (final item in value)
          if (item is Map) Map<String, Object?>.from(item)
      ]
    : const [];

final class BulletinBountyClaim {
  final String id, bountyId, termsHash, claimant, claimantHandle, status;
  final int? termsVersion;
  final bool termsBindingIsExplicit;
  final List<BulletinBountySubmission> submissions;
  const BulletinBountyClaim(
      {required this.id,
      required this.bountyId,
      required this.termsVersion,
      required this.termsHash,
      required this.claimant,
      required this.claimantHandle,
      required this.status,
      required this.termsBindingIsExplicit,
      required this.submissions});
  factory BulletinBountyClaim.fromJson(Map<String, Object?> json) =>
      BulletinBountyClaim(
        id: _text(json['id']),
        bountyId: _text(json['bounty_id']),
        termsVersion: _int(json['terms_version']),
        termsHash: _text(json['terms_hash']),
        claimant: _text(json['claimant']),
        claimantHandle: _text(json['claimant_handle']),
        status: _text(json['status']),
        termsBindingIsExplicit: json['terms_binding_is_explicit'] == true,
        submissions: _maps(json['submissions'])
            .map(BulletinBountySubmission.fromJson)
            .toList(growable: false),
      );
}

final class BulletinBountySubmission {
  final String id, claimId, status, proofText;
  final bool sourceAnchorsCheckedByBoard, noFetchPerformed;
  final List<BulletinBountySourceAnchor> sourceAnchors;
  final BulletinBountyReview? review;
  const BulletinBountySubmission(
      {required this.id,
      required this.claimId,
      required this.status,
      required this.proofText,
      required this.sourceAnchors,
      required this.sourceAnchorsCheckedByBoard,
      required this.noFetchPerformed,
      this.review});
  factory BulletinBountySubmission.fromJson(Map<String, Object?> json) =>
      BulletinBountySubmission(
        id: _text(json['id']),
        claimId: _text(json['claim_id']),
        status: _text(json['status']),
        proofText: _text(json['proof_text']),
        sourceAnchors: _maps(json['source_anchors'])
            .map(BulletinBountySourceAnchor.fromJson)
            .toList(growable: false),
        sourceAnchorsCheckedByBoard:
            json['source_anchors_checked_by_board'] == true,
        noFetchPerformed: json['no_fetch_performed'] == true,
        review: json['review'] is Map
            ? BulletinBountyReview.fromJson(_map(json['review']))
            : null,
      );
}

final class BulletinBountySourceAnchor {
  final String source, locator, note;
  final String? sourceHash;
  final bool missing, redacted, invalidSourceHash;
  const BulletinBountySourceAnchor(
      {required this.source,
      required this.sourceHash,
      required this.invalidSourceHash,
      required this.locator,
      required this.missing,
      required this.redacted,
      required this.note});
  factory BulletinBountySourceAnchor.fromJson(Map<String, Object?> json) {
    final hash = _text(json['source_hash']);
    final validHash = hash.isNotEmpty && _sha64.hasMatch(hash);
    return BulletinBountySourceAnchor(
      source: _text(json['source']),
      sourceHash: validHash ? hash : null,
      invalidSourceHash: hash.isNotEmpty && !validHash,
      missing: json['missing'] == true,
      redacted: json['redacted'] == true,
      note: _text(json['note']),
      locator: _locator(json),
    );
  }
  static String _locator(Map<String, Object?> json) {
    final line = _map(json['line_range']);
    if (line.isNotEmpty) {
      return 'lines ${line['start'] ?? '?'}-${line['end'] ?? '?'}';
    }
    final chars = _map(json['char_range']);
    if (chars.isNotEmpty) {
      return 'chars ${chars['start'] ?? '?'}-${chars['end'] ?? '?'}';
    }
    final pointer = _text(json['json_pointer']);
    return pointer.isEmpty ? 'locator unavailable' : pointer;
  }
}

final class BulletinBountyReview {
  final String id, decision, reviewNote, paymentState, externalPaymentState;
  final bool? verifiedPaid;
  final bool paymentVerifiedByBoard, establishesPayment;
  const BulletinBountyReview(
      {required this.id,
      required this.decision,
      required this.reviewNote,
      required this.verifiedPaid,
      required this.paymentVerifiedByBoard,
      required this.externalPaymentState,
      required this.paymentState,
      required this.establishesPayment});
  factory BulletinBountyReview.fromJson(Map<String, Object?> json) =>
      BulletinBountyReview(
        id: _text(json['id']),
        decision: _text(json['decision']),
        reviewNote: _text(json['review_note']),
        verifiedPaid: json['verified_paid'] is bool
            ? json['verified_paid'] as bool
            : null,
        paymentVerifiedByBoard: _bool(json['payment_verified_by_board']),
        externalPaymentState: _text(json['external_payment_state']),
        paymentState: _text(json['payment_state']),
        establishesPayment: _bool(json['establishes_payment']),
      );
}

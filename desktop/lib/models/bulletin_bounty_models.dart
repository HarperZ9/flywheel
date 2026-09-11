import 'bulletin_bounty_activity.dart';

export 'bulletin_bounty_activity.dart';

final _isoCurrency = RegExp(r'^[A-Z]{3}$');

String _text(Object? value) => value is String ? value : '';
int? _int(Object? value) => value is int ? value : null;
bool _bool(Object? value) => value is bool && value;
Map<String, Object?> _map(Object? value) =>
    value is Map ? Map<String, Object?>.from(value) : const {};
List<Map<String, Object?>> _maps(Object? value) => value is List
    ? [
        for (final item in value)
          if (item is Map) Map<String, Object?>.from(item)
      ]
    : const [];

final class BulletinBountyList {
  final List<BulletinBounty> bounties;
  final bool contentIsUntrusted;
  final String? nextBefore;
  const BulletinBountyList(
      this.bounties, this.contentIsUntrusted, this.nextBefore);

  factory BulletinBountyList.fromJson(Map<String, Object?> json) {
    final rows = _maps(json['bounties'] ?? json['items'])
        .map(BulletinBounty.fromJson)
        .where((bounty) => bounty.id.isNotEmpty)
        .toList(growable: false);
    return BulletinBountyList(
        rows, json['content_is_untrusted'] == true, _text(json['next_before']));
  }
}

final class BulletinBountyDetail {
  final BulletinBounty bounty;
  final bool contentIsUntrusted;
  const BulletinBountyDetail(this.bounty, this.contentIsUntrusted);

  factory BulletinBountyDetail.fromJson(Map<String, Object?> json) =>
      BulletinBountyDetail(BulletinBounty.fromJson(_map(json['bounty'])),
          json['content_is_untrusted'] == true);
}

final class BulletinBounty {
  final String id, requester, requesterHandle, room, status;
  final int? currentTermsVersion;
  final bool contentIsUntrusted;
  final BulletinBountyTerms terms;
  final BulletinBountyPayment payment;
  final List<BulletinBountyClaim> claims;
  const BulletinBounty(
      {required this.id,
      required this.requester,
      required this.requesterHandle,
      required this.room,
      required this.status,
      required this.currentTermsVersion,
      required this.contentIsUntrusted,
      required this.terms,
      required this.payment,
      required this.claims});

  factory BulletinBounty.fromJson(Map<String, Object?> json) => BulletinBounty(
        id: _text(json['id']),
        requester: _text(json['requester']),
        requesterHandle: _text(json['requester_handle']),
        room: _text(json['room']),
        status: _text(json['status']),
        currentTermsVersion: _int(json['current_terms_version']),
        contentIsUntrusted: json['content_is_untrusted'] == true,
        terms: BulletinBountyTerms.fromJson(_map(json['terms'])),
        payment: BulletinBountyPayment.fromJson(_map(json['payment'])),
        claims: _maps(json['claims'])
            .map(BulletinBountyClaim.fromJson)
            .toList(growable: false),
      );
}

final class BulletinBountyTerms {
  final int? version, deadlineAt, claimLimit, offerAmountMinor;
  final String termsHash,
      signature,
      title,
      summary,
      body,
      acceptanceCriteria,
      offerCurrency;
  const BulletinBountyTerms(
      {required this.version,
      required this.termsHash,
      required this.signature,
      required this.title,
      required this.summary,
      required this.body,
      required this.acceptanceCriteria,
      required this.offerAmountMinor,
      required this.offerCurrency,
      required this.deadlineAt,
      required this.claimLimit});

  factory BulletinBountyTerms.fromJson(Map<String, Object?> json) =>
      BulletinBountyTerms(
        version: _int(json['version']),
        termsHash: _text(json['terms_hash']),
        signature: _text(json['signature']),
        title: _text(json['title']),
        summary: _text(json['summary']),
        body: _text(json['body']),
        acceptanceCriteria: _text(json['acceptance_criteria']),
        offerAmountMinor: _int(json['offer_amount_minor']),
        offerCurrency: _text(json['offer_currency']).toUpperCase(),
        deadlineAt: _int(json['deadline_at']),
        claimLimit: _int(json['claim_limit']),
      );
}

final class BulletinBountyPayment {
  static const _minorUnits = {
    'USD': 2,
    'EUR': 2,
    'GBP': 2,
    'CAD': 2,
    'AUD': 2,
    'NZD': 2,
    'CHF': 2,
    'JPY': 0,
    'KRW': 0,
    'VND': 0,
    'BHD': 3,
    'JOD': 3,
    'KWD': 3,
    'OMR': 3,
    'TND': 3
  };
  final String state, capability, offeredCurrency, externalPaymentState;
  final int? offeredAmountMinor;
  final bool offerVerified, escrowed, paymentVerifiedByBoard;
  final bool? verifiedPaid;
  const BulletinBountyPayment(
      {required this.state,
      required this.capability,
      required this.offerVerified,
      required this.escrowed,
      required this.offeredAmountMinor,
      required this.offeredCurrency,
      required this.verifiedPaid,
      required this.paymentVerifiedByBoard,
      required this.externalPaymentState});

  factory BulletinBountyPayment.fromJson(Map<String, Object?> json) =>
      BulletinBountyPayment(
        state: _text(json['state'] ?? json['payment_state']),
        capability: _text(json['capability']),
        offerVerified: _bool(json['offer_verified']),
        escrowed: _bool(json['escrowed']),
        offeredAmountMinor: _int(json['offered_amount_minor']),
        offeredCurrency: _text(json['offered_currency']).toUpperCase(),
        verifiedPaid: json['verified_paid'] is bool
            ? json['verified_paid'] as bool
            : null,
        paymentVerifiedByBoard: _bool(json['payment_verified_by_board']),
        externalPaymentState: _text(json['external_payment_state']),
      );

  String get amountLabel {
    final amount = offeredAmountMinor;
    if (amount == null) return 'amount unavailable';
    final code = offeredCurrency;
    final digits = _minorUnits[code];
    if (_isoCurrency.hasMatch(code) && digits != null) {
      final sign = amount < 0 ? '-' : '';
      final abs = amount.abs().toString().padLeft(digits + 1, '0');
      final units = digits == 0
          ? abs
          : '${abs.substring(0, abs.length - digits)}.${abs.substring(abs.length - digits)}';
      return '$code $sign$units';
    }
    return code.isEmpty ? '$amount minor units' : '$amount minor units $code';
  }

  String get paymentLabel {
    final stateLabel =
        (state.isEmpty ? 'payment unknown' : state).replaceAll('_', ' ');
    final external = externalPaymentState.isEmpty
        ? 'external payment unknown'
        : 'external payment ${externalPaymentState.replaceAll('_', ' ')}';
    final board = paymentVerifiedByBoard
        ? 'board verified payment'
        : 'no board payment verification';
    final custody = escrowed ? 'escrow reported' : 'no escrow or settlement';
    return '$stateLabel · $external · $board · $custody';
  }
}

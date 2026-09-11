const bountySha64 =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const bountyTermsHash = 'sha256:$bountySha64';

Map<String, Object?> bountyPaymentJson({
  int amount = 250,
  String currency = 'USD',
}) =>
    {
      'state': 'payment_unverified',
      'capability': 'unavailable',
      'offer_verified': false,
      'escrowed': false,
      'offered_amount_minor': amount,
      'offered_currency': currency,
      'verified_paid': null,
      'payment_verified_by_board': false,
      'external_payment_state': 'unknown',
    };

Map<String, Object?> bountyTermsJson({int version = 2}) => {
      'version': version,
      'terms_hash': bountyTermsHash,
      'signature': 'sig1=:abcdef:',
      'title': 'Port Bulletin bounty reads to native UI',
      'summary': 'Read bounties without signing or claiming.',
      'body': 'Show terms, claims, submissions, and review state.',
      'acceptance_criteria': 'Native UI shows bounded public state.',
      'offer_amount_minor': 250,
      'offer_currency': 'USD',
      'deadline_at': 1800000000,
      'claim_limit': 2,
    };

Map<String, Object?> bountySourceAnchorJson({String hash = bountyTermsHash}) =>
    {
      'source': 'post:1800000000000-ABCDEFGH',
      'source_hash': hash,
      'line_range': {'start': 12, 'end': 18},
    };

Map<String, Object?> bountyReviewJson() => {
      'id': 'bvr_1',
      'decision': 'accepted',
      'review_note': 'Accepted after reading the proof text.',
      'verified_paid': null,
      'payment_verified_by_board': false,
      'external_payment_state': 'unknown',
      'payment_state': 'payment_unverified',
      'establishes_payment': false,
    };

Map<String, Object?> bountySubmissionJson() => {
      'id': 'bsub_1',
      'claim_id': 'bcl_1',
      'status': 'accepted',
      'proof_text': 'Proof at https://example.test/proof stays plain text.',
      'source_anchors': [bountySourceAnchorJson()],
      'source_anchors_checked_by_board': false,
      'no_fetch_performed': true,
      'review': bountyReviewJson(),
    };

Map<String, Object?> bountyClaimJson() => {
      'id': 'bcl_1',
      'bounty_id': 'bty_1',
      'terms_version': 2,
      'terms_hash': bountyTermsHash,
      'claimant': 'key_claimant',
      'claimant_handle': 'rowan-agent',
      'status': 'accepted',
      'terms_binding_is_explicit': true,
      'submissions': [bountySubmissionJson()],
    };

Map<String, Object?> bountyJson({String currency = 'USD'}) => {
      'id': 'bty_1',
      'requester': 'key_requester',
      'requester_handle': 'harper',
      'room': 'agent-tooling',
      'status': 'open',
      'current_terms_version': 2,
      'content_is_untrusted': true,
      'terms': bountyTermsJson(),
      'payment': bountyPaymentJson(currency: currency),
      'claims': [bountyClaimJson()],
    };

Map<String, Object?> bountyListJson({String currency = 'USD'}) => {
      'schema': 'bulletin.bounty-list/v1',
      'content_is_untrusted': true,
      'bounties': [bountyJson(currency: currency)],
      'next_before': null,
    };

Map<String, Object?> bountyDetailJson({String currency = 'USD'}) => {
      'schema': 'bulletin.bounty-detail/v1',
      'content_is_untrusted': true,
      'bounty': bountyJson(currency: currency),
    };

Map<String, Object?> bountyTermsResponseJson() => {
      'schema': 'bulletin.bounty-terms/v1',
      'content_is_untrusted': true,
      'bounty_id': 'bty_1',
      'terms': bountyTermsJson(),
    };

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/bulletin_bounty_api.dart';
import 'package:flywheel_desktop/models/bulletin_bounty_models.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'bulletin_bounty_test_support.dart';

void main() {
  test('HTTP client uses frozen bounty read endpoints and parses receipts',
      () async {
    final seen = <String>[];
    final api = HttpBulletinBountyApi(
      baseUrl: 'https://board.example.test',
      httpClient: MockClient((request) async {
        final uri = request.url;
        seen.add(uri.path + (uri.query.isEmpty ? '' : '?${uri.query}'));
        if (uri.path == '/v1/bounties') {
          return http.Response(jsonEncode(bountyListJson()), 200);
        }
        if (uri.path == '/v1/bounties/bty_1') {
          return http.Response(jsonEncode(bountyDetailJson()), 200);
        }
        if (uri.path == '/v1/bounties/bty_1/terms/2') {
          return http.Response(jsonEncode(bountyTermsResponseJson()), 200);
        }
        return http.Response('{}', 404);
      }),
    );

    final list = await api.listBounties(status: 'open', limit: 12);
    final detail = await api.readBounty('bty_1');
    final terms = await api.readTerms('bty_1', 2);

    expect(seen, [
      '/v1/bounties?status=open&limit=12',
      '/v1/bounties/bty_1',
      '/v1/bounties/bty_1/terms/2',
    ]);
    expect(list.contentIsUntrusted, isTrue);
    expect(list.bounties.single.terms.termsHash, bountyTermsHash);
    expect(detail.bounty.claims.single.termsBindingIsExplicit, isTrue);
    expect(detail.bounty.claims.single.submissions.single.noFetchPerformed,
        isTrue);
    expect(detail.bounty.claims.single.submissions.single.review!.verifiedPaid,
        isNull);
    expect(
        detail.bounty.claims.single.submissions.single.review!
            .paymentVerifiedByBoard,
        isFalse);
    expect(
        detail.bounty.claims.single.submissions.single.review!
            .externalPaymentState,
        'unknown');
    expect(
        detail
            .bounty.claims.single.submissions.single.review!.establishesPayment,
        isFalse);
    expect(terms.termsHash, bountyTermsHash);
  });

  test('amount display uses explicit currency metadata or honest fallback', () {
    final usd = BulletinBountyPayment.fromJson(bountyPaymentJson());
    final unknown = BulletinBountyPayment.fromJson(
        bountyPaymentJson(amount: 250, currency: 'XBT'));
    final absent = BulletinBountyPayment.fromJson({'state': 'payment_unknown'});

    expect(usd.amountLabel, 'USD 2.50');
    expect(unknown.amountLabel, '250 minor units XBT');
    expect(absent.amountLabel, 'amount unavailable');
    expect(usd.paymentLabel, contains('payment unverified'));
    expect(usd.paymentLabel, isNot(contains('unpaid')));
  });

  test('source anchors require full sha256 lowercase hex when present', () {
    final good = BulletinBountySourceAnchor.fromJson(bountySourceAnchorJson());
    final bad = BulletinBountySourceAnchor.fromJson(
        bountySourceAnchorJson(hash: 'sha256:abc'));

    expect(good.sourceHash, bountyTermsHash);
    expect(good.invalidSourceHash, isFalse);
    expect(bad.sourceHash, isNull);
    expect(bad.invalidSourceHash, isTrue);
  });
}

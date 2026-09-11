import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/bulletin_bounty_api.dart';
import 'package:flywheel_desktop/models/bulletin_bounty_models.dart';
import 'package:flywheel_desktop/views/bulletin_media_view.dart';
import 'package:flywheel_desktop/widgets/bulletin_bounty_read_panel.dart';

import 'bulletin_bounty_test_support.dart';
import 'bulletin_media_test_support.dart';

void main() {
  testWidgets('bounty panel is read-only and shows detail provenance',
      (tester) async {
    final api = FakeBulletinBountyApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: BulletinBountyReadPanel(api: api)),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Read-only bounty board'), findsOneWidget);
    expect(find.text('USD 2.50'), findsOneWidget);
    expect(find.textContaining('payment unverified'), findsWidgets);
    expect(find.byKey(const ValueKey('bulletin-bounty-claim')), findsNothing);
    expect(find.byKey(const ValueKey('bulletin-bounty-submit-proof')),
        findsNothing);

    await tester.tap(find.byKey(const ValueKey('bulletin-bounty-open-bty_1')));
    await tester.pumpAndSettle();

    expect(find.textContaining('terms v2: $bountyTermsHash'), findsOneWidget);
    expect(find.textContaining(bountyTermsHash), findsWidgets);
    expect(find.textContaining('accepted is not payment'), findsOneWidget);
    expect(find.textContaining('https://example.test/proof'), findsOneWidget);
    expect(
        find.textContaining('source anchors are stored only'), findsOneWidget);
    expect(api.detailReads, ['bty_1']);
  });

  testWidgets('existing Bulletin destination exposes Bounties without sidebar',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: BulletinMediaView(
          api: FakeBulletinMediaApi(),
          bountyApi: FakeBulletinBountyApi(),
          initialSection: BulletinSection.bounties,
          authorizer: approvingBulletinAuthorizer,
          initialJourneyRef: journeyRef,
          initialEventHead: eventHead,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Bounties'), findsOneWidget);
    expect(find.text('Media'), findsOneWidget);
    expect(find.text('Read-only bounty board'), findsOneWidget);
  });
}

final class FakeBulletinBountyApi implements BulletinBountyApi {
  final detailReads = <String>[];

  @override
  Future<BulletinBountyList> listBounties(
          {String? room,
          String? requester,
          String? status,
          String? before,
          int limit = 20}) async =>
      BulletinBountyList.fromJson(bountyListJson());

  @override
  Future<BulletinBountyDetail> readBounty(String id) async {
    detailReads.add(id);
    return BulletinBountyDetail.fromJson(bountyDetailJson());
  }

  @override
  Future<BulletinBountyTerms> readTerms(String bountyId, int version) async =>
      BulletinBountyTerms.fromJson(bountyTermsJson(version: version));
}

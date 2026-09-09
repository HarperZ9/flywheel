import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/bulletin_media_models.dart';
import 'package:flywheel_desktop/views/bulletin_media_view.dart';

import 'bulletin_media_test_support.dart';
import 'bulletin_media_widget_test_support.dart';

const _destination = 'https://bulletin.example.test';

void main() {
  testWidgets(
      'operator selects run artifact, previews, approves, and sees result',
      (tester) async {
    final api = FakeBulletinMediaApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: BulletinMediaView(
        api: api,
        authorizer: approvingBulletinAuthorizer,
        initialJourneyRef: journeyRef,
        initialEventHead: eventHead,
      )),
    ));
    await tester.pumpAndSettle();

    await tester.tap(keyed('bulletin-load-runs'));
    await tester.pumpAndSettle();
    await tester.tap(keyed('bulletin-run-run_20260909T000000_abcdef123456'));
    await tester.pumpAndSettle();
    expect(find.text('BULLETIN_AGENT_JWK'), findsOneWidget);
    expect(find.text(credRef), findsWidgets);
    await tester.enterText(keyed('bulletin-destination'), _destination);
    await tester.ensureVisible(keyed('bulletin-load-artifacts'));
    await tester.tap(keyed('bulletin-load-artifacts'));
    await tester.pumpAndSettle();
    await tester.tap(keyed('bulletin-artifact-artifact_meme_png'));
    await tester.enterText(keyed('bulletin-title'), 'Public title');
    await tester.enterText(
        keyed('bulletin-body'), 'A public music/art update.');
    await tester.enterText(
        keyed('bulletin-alt-artifact_meme_png'), 'Alt text for one pixel.');
    await tester.ensureVisible(keyed('bulletin-preview'));
    await tester.tap(keyed('bulletin-preview'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(api.lastDraft?.runId, 'run_20260909T000000_abcdef123456');
    expect(api.lastDraft?.credentialRef, credRef);
    expect(api.lastDraft?.media.single.alt, 'Alt text for one pixel.');
    expect(api.lastDraft?.sourceAttribution, 'Selected from a Flywheel run.');
    expect(find.text('The final public post body.'), findsOneWidget);

    await tester.ensureVisible(keyed('bulletin-publish'));
    await tester.tap(keyed('bulletin-publish'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(api.lastFinalBody?['grant_ref'], grantRef);
    expect(find.text('Posted readback matched.'), findsOneWidget);
  });

  testWidgets('changed draft blocks reuse of stale approval operation',
      (tester) async {
    final api = FakeBulletinMediaApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: BulletinMediaView(
        api: api,
        authorizer: approvingBulletinAuthorizer,
        initialJourneyRef: journeyRef,
        initialEventHead: eventHead,
      )),
    ));
    await tester.pumpAndSettle();

    await tester.enterText(keyed('bulletin-run-id'), 'run_artifact_001');
    await tester.enterText(keyed('bulletin-destination'), _destination);
    await tester.ensureVisible(keyed('bulletin-load-artifacts'));
    await tester.tap(keyed('bulletin-load-artifacts'));
    await tester.pumpAndSettle();
    await tester.tap(keyed('bulletin-artifact-artifact_meme_png'));
    await tester.enterText(keyed('bulletin-title'), 'Public title');
    await tester.enterText(keyed('bulletin-body'), 'Original public body.');
    await tester.enterText(
        keyed('bulletin-alt-artifact_meme_png'), 'Original alt.');
    await tester.ensureVisible(keyed('bulletin-preview'));
    await tester.tap(keyed('bulletin-preview'));
    await tester.pump(const Duration(milliseconds: 50));

    await tester.enterText(keyed('bulletin-body'), 'Changed public body.');
    await tester.ensureVisible(keyed('bulletin-publish'));
    await tester.tap(keyed('bulletin-publish'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(api.lastFinalBody, isNull);
    expect(find.textContaining('OPERATION_CHANGED'), findsOneWidget);
  });

  testWidgets('partial publication result remains visibly incomplete',
      (tester) async {
    final api = FakeBulletinMediaApi(
      result: BulletinMediaPublishResult.fromJson(
          publishResultJson('media_uploaded_post_failed')),
    );
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: BulletinMediaView(
        api: api,
        authorizer: approvingBulletinAuthorizer,
        initialJourneyRef: journeyRef,
        initialEventHead: eventHead,
      )),
    ));
    await tester.pumpAndSettle();

    await tester.enterText(keyed('bulletin-run-id'), 'run_artifact_001');
    await tester.enterText(keyed('bulletin-destination'), _destination);
    await tester.ensureVisible(keyed('bulletin-load-artifacts'));
    await tester.tap(keyed('bulletin-load-artifacts'));
    await tester.pumpAndSettle();
    await tester.tap(keyed('bulletin-artifact-artifact_meme_png'));
    await tester.enterText(keyed('bulletin-title'), 'Public title');
    await tester.enterText(keyed('bulletin-body'), 'A public post.');
    await tester.enterText(keyed('bulletin-alt-artifact_meme_png'), 'Alt.');
    await tester.ensureVisible(keyed('bulletin-preview'));
    await tester.tap(keyed('bulletin-preview'));
    await tester.pump(const Duration(milliseconds: 50));
    await tester.ensureVisible(keyed('bulletin-publish'));
    await tester.tap(keyed('bulletin-publish'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Media uploaded; post failed.'), findsOneWidget);
    expect(find.textContaining('not complete'), findsOneWidget);
  });

  testWidgets('absent Bulletin handle stops before preview', (tester) async {
    final api = FakeBulletinMediaApi(credentialRows: const []);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: BulletinMediaView(
        api: api,
        authorizer: approvingBulletinAuthorizer,
        initialJourneyRef: journeyRef,
        initialEventHead: eventHead,
      )),
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining('No BULLETIN_AGENT_JWK credential handle'),
        findsOneWidget);
    await tester.enterText(keyed('bulletin-run-id'), 'run_artifact_001');
    await tester.enterText(keyed('bulletin-destination'), _destination);
    await tester.ensureVisible(keyed('bulletin-load-artifacts'));
    await tester.tap(keyed('bulletin-load-artifacts'));
    await tester.pumpAndSettle();
    await tester.tap(keyed('bulletin-artifact-artifact_meme_png'));
    await tester.enterText(keyed('bulletin-title'), 'Public title');
    await tester.enterText(keyed('bulletin-body'), 'A public post.');
    await tester.enterText(keyed('bulletin-alt-artifact_meme_png'), 'Alt.');
    await tester.ensureVisible(keyed('bulletin-preview'));
    await tester.tap(keyed('bulletin-preview'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Select a BULLETIN_AGENT_JWK credential handle before preview.'),
        findsOneWidget);
    expect(api.previewCalls, 0);
    expect(api.lastDraft, isNull);
  });

  testWidgets('malformed credential handle response stays metadata-only',
      (tester) async {
    final api = FakeBulletinMediaApi(
        credentialError: const FormatException('invalid credential handles'));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: BulletinMediaView(
        api: api,
        authorizer: approvingBulletinAuthorizer,
        initialJourneyRef: journeyRef,
        initialEventHead: eventHead,
      )),
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining('Credential handles could not be read'),
        findsOneWidget);
    expect(find.text(credRef), findsNothing);
    expect(find.textContaining('secret'), findsNothing);
  });

  testWidgets('blank destination stops before backend preview', (tester) async {
    final api = FakeBulletinMediaApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: BulletinMediaView(
        api: api,
        authorizer: approvingBulletinAuthorizer,
        initialJourneyRef: journeyRef,
        initialEventHead: eventHead,
      )),
    ));
    await tester.pumpAndSettle();

    await tester.enterText(keyed('bulletin-run-id'), 'run_artifact_001');
    await tester.ensureVisible(keyed('bulletin-load-artifacts'));
    await tester.tap(keyed('bulletin-load-artifacts'));
    await tester.pumpAndSettle();
    await tester.tap(keyed('bulletin-artifact-artifact_meme_png'));
    await tester.enterText(keyed('bulletin-title'), 'Public title');
    await tester.enterText(keyed('bulletin-body'), 'A public post.');
    await tester.enterText(keyed('bulletin-alt-artifact_meme_png'), 'Alt.');
    await tester.ensureVisible(keyed('bulletin-preview'));
    await tester.tap(keyed('bulletin-preview'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Configure a Bulletin destination before preview.'),
        findsOneWidget);
    expect(api.previewCalls, 0);
    expect(api.lastDraft, isNull);
  });

  testWidgets('source default is truthful about selection only', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: BulletinMediaView(
        api: FakeBulletinMediaApi(),
        authorizer: approvingBulletinAuthorizer,
        initialJourneyRef: journeyRef,
        initialEventHead: eventHead,
      )),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Selected from a Flywheel run.'), findsOneWidget);
    expect(find.text('Owner-created run artifact.'), findsNothing);
  });
}

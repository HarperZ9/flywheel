import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/models/approval_inbox_models.dart';
import 'package:flywheel_desktop/views/approvals_inbox_view.dart';
import 'package:flywheel_desktop/widgets/fw.dart';

import 'approval_inbox_test_support.dart';

void main() {
  testWidgets('older gateway shows upgrade required and no approve fallback',
      (tester) async {
    final api = FakeInboxApi(
        capabilities: GatewayGrantCapabilities.fromJson(
      const {'schema': 'flywheel.gateway-grant-capabilities/v1'},
    ));
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.textContaining('upgrade_required'), findsOneWidget);
    expect(find.text('Approve reviewed'), findsNothing);
    expect(api.approveCalls, isEmpty);
  });

  testWidgets('missing capability route is treated as upgrade required',
      (tester) async {
    final api = FakeInboxApi(
        capabilities: GatewayGrantCapabilities.fromJson(const {}),
        capabilitiesError: const GatewayGrantException(
            'NOT_FOUND', 'Gateway operation was not found'));
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.textContaining('upgrade_required'), findsOneWidget);
    expect(find.text('Approve reviewed'), findsNothing);
    expect(api.approveCalls, isEmpty);
  });

  testWidgets('pending row reads exact review before enabling approve',
      (tester) async {
    final api = FakeInboxApi.ready();
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.text(proposalRef), findsOneWidget);
    expect(find.text('Approve reviewed'), findsNothing);
    await tester.tap(find.text(proposalRef));
    await tester.pumpAndSettle();

    expect(api.readCalls, [proposalRef]);
    expect(find.textContaining('"nested"'), findsOneWidget);
    expect(find.textContaining('cred_aaaaaaaa'), findsOneWidget);
    await scrollActionIntoView(tester, 'Approve reviewed');
    await tester.tap(find.text('Approve reviewed'));
    await tester.pumpAndSettle();

    expect(api.approveCalls, [(proposalRef, reviewSha)]);
    expect(api.legacyApproveCalls, isEmpty);
  });

  testWidgets('review unavailable rows cannot approve but can reject',
      (tester) async {
    final api = FakeInboxApi.ready(pages: [
      listPage(items: [listItem(reviewAvailable: false)])
    ], reads: {
      proposalRef: readUnavailable()
    });
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();
    await tester.tap(find.text(proposalRef));
    await tester.pumpAndSettle();

    expect(find.textContaining('OPERATION_REVIEW_TOO_LARGE'), findsOneWidget);
    expect(find.text('Approve reviewed'), findsNothing);
    await scrollActionIntoView(tester, 'Reject');
    await tester.tap(find.text('Reject'));
    await tester.pumpAndSettle();
    expect(api.rejectCalls, [(proposalRef, approvalHash)]);
  });

  testWidgets('reject is durable while dismiss is local only', (tester) async {
    final api = FakeInboxApi.ready();
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();
    await tester.tap(find.text(proposalRef));
    await tester.pumpAndSettle();

    await scrollActionIntoView(tester, 'Dismiss');
    await tester.tap(find.text('Dismiss'));
    await tester.pumpAndSettle();
    expect(api.rejectCalls, isEmpty);
    expect(find.text(proposalRef), findsNothing);

    await tester.tap(find.text('Refresh'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(proposalRef));
    await tester.pumpAndSettle();
    await scrollActionIntoView(tester, 'Reject');
    await tester.tap(find.text('Reject'));
    await tester.pumpAndSettle();
    expect(api.rejectCalls, [(proposalRef, approvalHash)]);
  });

  testWidgets('active work separates active terminal unknown and errors',
      (tester) async {
    final api = FakeInboxApi.ready(
        activeWork: ActiveWorkSnapshot(items: [
      ActiveWorkItem('run-active-1', 'running', ActiveWorkKind.active),
      ActiveWorkItem('run-done-1', 'completed', ActiveWorkKind.terminal),
      ActiveWorkItem('run-weird-1', 'paused', ActiveWorkKind.unknown),
    ]));
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.text('Active relay runs'), findsOneWidget);
    expect(find.textContaining('run-active-1'), findsOneWidget);
    expect(find.text('Recent terminal relay runs'), findsOneWidget);
    expect(find.textContaining('run-done-1'), findsOneWidget);
    expect(find.text('Unknown relay run status'), findsOneWidget);
    expect(find.textContaining('run-weird-1'), findsOneWidget);
    final dotStatuses = tester
        .widgetList<VerdictDot>(find.byType(VerdictDot))
        .map((dot) => dot.status);
    expect(dotStatuses, ['live', 'verified', 'unverifiable']);
  });

  testWidgets('active fetch failure is not rendered as an empty state',
      (tester) async {
    final api = FakeInboxApi.ready(
        activeWork: const ActiveWorkSnapshot.unavailable(
            'Active work status unavailable'));
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(
        find.textContaining('Active work status unavailable'), findsOneWidget);
    expect(find.text('No active relay runs reported.'), findsNothing);
  });

  testWidgets('pending proposal operation refs are not cancellation authority',
      (tester) async {
    final api = FakeInboxApi.ready();
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();
    await tester.tap(find.text(proposalRef));
    await tester.pumpAndSettle();

    expect(find.text('Cancel active work'), findsNothing);
    expect(find.textContaining('Open Relay or Journey'), findsOneWidget);
    await scrollActionIntoView(tester, 'Reject');
    await tester.tap(find.text('Reject'));
    await tester.pumpAndSettle();
    expect(api.rejectCalls, [(proposalRef, approvalHash)]);
  });

  testWidgets('index incomplete empty page stays recovery limited',
      (tester) async {
    final api = FakeInboxApi.ready(pages: [
      listPage(
          items: const [],
          indexComplete: false,
          listStatus: 'legacy_index_required'),
    ]);
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.textContaining('recovery-limited'), findsOneWidget);
    expect(find.textContaining('legacy index required'), findsOneWidget);
    expect(find.text('No pending proposals.'), findsNothing);
  });

  testWidgets('complete empty index page does not claim global absence',
      (tester) async {
    final api = FakeInboxApi.ready(pages: [
      listPage(items: const []),
    ]);
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.text('No indexed pending proposals.'), findsOneWidget);
    expect(find.text('No pending proposals.'), findsNothing);
  });

  testWidgets('index mutation pending uses a safe incomplete message',
      (tester) async {
    final api = FakeInboxApi.ready(pages: [
      listPage(
          items: const [],
          indexComplete: false,
          listStatus: 'index_mutation_pending'),
    ]);
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.textContaining('recovery-limited'), findsOneWidget);
    expect(find.textContaining('index mutation pending'), findsOneWidget);
    expect(find.text('No pending proposals.'), findsNothing);
  });

  testWidgets('explicit recovery required status shows typed reason',
      (tester) async {
    final api = FakeInboxApi.ready(pages: [
      listPage(
          items: const [],
          indexComplete: false,
          listStatus: 'recovery_required',
          recoveryRequired: 'SCAN_LIMIT_EXCEEDED'),
    ]);
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.textContaining('recovery required'), findsOneWidget);
    expect(find.textContaining('SCAN_LIMIT_EXCEEDED'), findsOneWidget);
    expect(find.text('No indexed pending proposals.'), findsNothing);
  });

  testWidgets('load more appends the next pending proposal page',
      (tester) async {
    final api = FakeInboxApi.ready(pages: [
      listPage(items: [listItem()], nextCursor: 'cursor-2'),
      listPage(items: [
        listItem(proposalRef: secondProposalRef, reviewSha: secondReviewSha)
      ]),
    ]);
    await tester
        .pumpWidget(wrapInbox(ApprovalsInboxView(api: api, alive: true)));
    await tester.pumpAndSettle();

    expect(find.text(proposalRef), findsOneWidget);
    expect(find.text(secondProposalRef), findsNothing);
    expect(find.text('Load more'), findsOneWidget);
    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(find.text(secondProposalRef), findsOneWidget);
    expect(api.listCursors, [null, 'cursor-2']);
  });
}

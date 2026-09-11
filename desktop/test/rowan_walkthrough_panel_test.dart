import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/rowan_walkthrough_models.dart';
import 'package:flywheel_desktop/widgets/rowan_walkthrough_panel.dart';

import 'rowan_walkthrough_test_support.dart';

void main() {
  testWidgets('walkthrough delegates run, reopen, and follow-up to shared host',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1000, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final host = FakeRowanOperationHost();
    var captionAttached = false;
    var followUpReviewed = false;

    await tester.pumpWidget(wrapRowanTest(RowanWalkthroughPanel(
      alive: true,
      operationHost: host,
      currentBinding: rowanTestBinding,
      captionBuilder: (_, __, operationHost) {
        captionAttached = identical(operationHost, host);
        return const Text('caption seam attached');
      },
      onReviewFollowUp: (_, __) async => followUpReviewed = true,
    )));
    await tester.pumpAndSettle();

    expect(find.text('Rowan live walkthrough'), findsOneWidget);
    expect(find.textContaining(rowanTestBinding.journeyRef), findsOneWidget);
    expect(find.text('caption seam attached'), findsOneWidget);
    expect(captionAttached, isTrue);
    expect(find.textContaining('Hidden internal chain-of-thought'),
        findsOneWidget);
    expect(find.textContaining('Guidance pause does not stop execution'),
        findsOneWidget);
    expect(rowanRunButton(tester).onPressed, isNull);
    expect(host.recoverCalls, 1);

    await tester.enterText(
      find.byKey(const Key('rowan-walkthrough-root')),
      r'C:\synthetic\repo',
    );
    await tester.tap(find.text('default model'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('qwen2.5-coder-14b-instruct'));
    await tester.pumpAndSettle();
    expect(rowanRunButton(tester).onPressed, isNotNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Run'));
    await tester.pumpAndSettle();

    expect(host.configuredScenario, rowanRetryPolicyWalkthroughScenario);
    expect(host.lastGoal, rowanRetryPolicyWalkthroughScenario.goal);
    expect(host.startCalls, 1);
    expect(host.endpoint, 'ollama');
    expect(host.selectedModel, 'qwen2.5-coder-14b-instruct');
    expect(host.workspaceRoot, r'C:\synthetic\repo');
    expect(rowanRunButton(tester).onPressed, isNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Running…'));
    await tester.pumpAndSettle();
    expect(host.startCalls, 1);

    final result = rowanTestResult(rowanTestAnswer);
    host.complete(result);
    await tester.pumpAndSettle();

    expect(find.textContaining('independent oracle matched'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Review bounded follow-up'),
        findsNothing);

    await tester
        .ensureVisible(find.widgetWithText(OutlinedButton, 'Reopen operation'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Reopen operation'));
    await tester.pumpAndSettle();
    expect(host.reconnectCalls, 1);
    expect(host.reconnectedFrom?.operationRef, rowanTestOperation);
    expect(
        find.textContaining('same operation record reopened'), findsOneWidget);

    await tester.ensureVisible(
        find.widgetWithText(OutlinedButton, 'Review bounded follow-up'));
    await tester.pumpAndSettle();
    await tester
        .tap(find.widgetWithText(OutlinedButton, 'Review bounded follow-up'));
    await tester.pumpAndSettle();
    expect(followUpReviewed, isTrue);
  });

  testWidgets('missing Journey binding blocks shared-host start',
      (tester) async {
    final host = FakeRowanOperationHost();

    await tester.pumpWidget(wrapRowanTest(RowanWalkthroughPanel(
      alive: true,
      operationHost: host,
    )));
    await tester.pumpAndSettle();
    host
      ..setWorkspaceRoot(r'C:\synthetic\repo')
      ..setModel('qwen2.5-coder-14b-instruct');
    await tester.pumpAndSettle();

    expect(find.textContaining('Select a Journey before approval'),
        findsOneWidget);
    expect(rowanRunButton(tester).onPressed, isNull);
    await tester.tap(find.widgetWithText(FilledButton, 'Run'));
    await tester.pumpAndSettle();
    expect(host.startCalls, 0);
  });
}

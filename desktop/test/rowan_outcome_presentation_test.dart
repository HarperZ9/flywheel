// A finished run's outcome is readable where the card is hosted.
//
// The outcome sits inside the assistant dialog's visible area, the headline
// reads correctly for one deliverable and for a stopped run, the verdict
// pills reach WCAG AA contrast, and screen readers are told when the
// outcome appears and when the handoff brief is copied.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/assistant/assistant_executor.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_handoff.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/run_outcome.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/assistant_panel.dart';
import 'package:flywheel_desktop/widgets/fw_verdict.dart';
import 'package:flywheel_desktop/widgets/rowan_completion_summary.dart';
import 'package:flywheel_desktop/widgets/rowan_handoff_button.dart';

import 'screen_capture_fonts.dart';

const _op = 'op_cccccccccccccccccccccccccccccccc';

Map<String, dynamic> _projection() => (jsonDecode(File(
            '../tests/fixtures/gateway_run_outcome/stopped_projection.json')
        .readAsStringSync()) as Map<String, dynamic>)['projection']
    as Map<String, dynamic>;

final class _Agent implements AgentSink {
  @override
  Future<String?> startTask(String goal) async => null;
}

final class _Device implements DeviceSink {
  @override
  Future<bool> open(String link) async => true;
}

RowanOperationController _stoppedRun() {
  final rowan = RowanOperationController(GatewayClient(
      httpClient: MockClient((_) async => http.Response('{}', 404))));
  addTearDown(rowan.dispose);
  final result = OperationResult.fromJson({
    'schema': operationResultSchema,
    'operation_ref': _op,
    'action': 'agent.run',
    'state': 'failed',
    'result': _projection(),
  });
  final snapshot = OperationSnapshot.fromJson({
    'schema': operationSnapshotSchema,
    'operation_ref': _op,
    'journey_ref': 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'event_head_sha256': 'a' * 64,
    'state': 'failed',
    'can_cancel': false,
    'terminal_event_ref': 'b' * 64,
    'result_sha256': result.canonicalSha256,
  });
  expect(rowan.operationState.acceptTerminal(snapshot, result), isTrue);
  return rowan;
}

RunCompletionOutcome _completion(List<Map<String, Object?>> items) {
  final counts = {
    for (final s in ['verified', 'claimed', 'failed'])
      s: items.where((i) => i['status'] == s).length
  };
  return RunCompletionOutcome.fromJson({
    'status': 'recorded',
    'verdict': counts['failed']! > 0
        ? 'failed'
        : counts['claimed']! > 0
            ? 'claimed'
            : 'verified',
    'counts': counts,
    'items': items,
    'items_omitted': 0,
    'unbacked_success_claim': false,
  });
}

Map<String, Object?> _item(String kind, String status, String? check, String detail) =>
    {'kind': kind, 'status': status, 'check': check, 'detail': detail};

void main() {
  setUpAll(loadScreenCaptureFonts);

  testWidgets('a stopped run shows its outcome inside the assistant dialog',
      (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final semantics = tester.ensureSemantics();
    final rowan = _stoppedRun();
    late BuildContext context;
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: Builder(builder: (ctx) {
        context = ctx;
        return const SizedBox.shrink();
      })),
    ));
    showAssistantPanel(context,
        executor: AssistantExecutor(agent: _Agent(), device: _Device()),
        rowan: rowan);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    final dialog = tester.getRect(find.byType(Dialog));
    final headline =
        tester.getRect(find.byKey(const Key('rowan-completion-headline')));
    expect(headline.top, greaterThan(dialog.top));
    expect(headline.bottom, lessThan(dialog.bottom));
    expect(tester.getRect(find.byKey(const Key('assistant-input'))).bottom,
        lessThan(dialog.bottom));
    expect(find.text('Not done: the run stopped before it finished.'),
        findsOneWidget);
    expect(tester.getSemantics(find.byKey(const Key('rowan-outcome-headline'))),
        isSemantics(isLiveRegion: true));
    semantics.dispose();
  });

  test('the headline reads for one deliverable and for a stopped run', () {
    final one = _completion(
        [_item('final_answer', 'claimed', null, 'no_check_ran')]);
    expect(completionHeadline(one),
        'Finished, not verified: no check covered 1 of 1 deliverable.');
    final stopped = _completion([
      _item('file', 'verified', 'file_hash_recheck', 'matches'),
      _item('final_answer', 'failed', 'run_state', 'AGENT_RUN_BUDGET_EXHAUSTED'),
    ]);
    expect(completionHeadline(stopped),
        'Not done: the run stopped before it finished.');
    final both = _completion([
      _item('file', 'failed', 'file_hash_recheck', 'missing'),
      _item('final_answer', 'failed', 'run_state', 'AGENT_RUN_BUDGET_EXHAUSTED'),
    ]);
    expect(completionHeadline(both),
        'Not done: the run stopped before it finished, and 1 of 2 '
        'deliverables failed a check.');
  });

  test('verdict pill text reaches 4.5:1 on its tint in both themes', () {
    for (final t in [FwTokens.light, FwTokens.dark]) {
      for (final status in ['verified', 'unverifiable', 'drift']) {
        final hue = t.statusColor(status);
        final ink = pillInk(t, hue);
        for (final ground in pillGrounds(t, hue)) {
          expect(contrastRatio(ink, ground), greaterThanOrEqualTo(4.5),
              reason: '$status on ${t == FwTokens.light ? 'light' : 'dark'}');
        }
      }
    }
    // A hue that already passes is left as it is, so color still means the
    // verdict.
    expect(pillInk(FwTokens.dark, FwTokens.dark.verified), FwTokens.dark.verified);
    expect(pillInk(FwTokens.light, FwTokens.light.verified),
        isNot(FwTokens.light.ink));
  });

  testWidgets('screen readers hear the outcome and the handoff copy',
      (tester) async {
    final handle = tester.ensureSemantics();
    tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (_) async => null);
    final api = HandoffApi(
        httpClient: MockClient((_) async => http.Response(
            jsonEncode({
              'schema': rowanHandoffSchema,
              'operation_ref': _op,
              'markdown': '# Handoff',
              'record_count': 5,
              'trace_head_sha256': 'd' * 64,
            }),
            200)));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: RowanHandoffButton(
                baseUrl: 'http://127.0.0.1:1', operationRef: _op, api: api))));
    await tester.tap(find.byKey(const Key('rowan-copy-handoff')));
    await tester.pumpAndSettle();
    expect(
        tester.getSemantics(find.byKey(const Key('rowan-handoff-note'))),
        isSemantics(
            isLiveRegion: true,
            label: 'Handoff brief copied: 5 trace records, head dddddddddddd. '
                'Not re-checked at export.'));
    handle.dispose();
  });
}

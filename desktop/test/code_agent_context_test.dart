import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/ide/agent_panel.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/code_view.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', '$_a$_a');
const _roster =
    '{"rows":[{"name":"local-public","backend":"local","credential":"local-none","provider_role":"","configured":true}]}';
const _approval = {
  'schema': 'flywheel.operation-grant-approval/v1',
  'grant_ref': 'gnt_$_a',
  'expires_at': '2026-08-15T12:02:00Z'
};
const _operationDone =
    'id: 1\r\nevent: terminal\r\ndata: {"snapshot":{"schema":"flywheel.gateway-operation-snapshot/v1","operation_ref":"op_$_a","journey_ref":"jrn_$_a","event_head_sha256":"$_a$_a","state":"completed","can_cancel":false,"terminal_event_ref":"$_a$_a","result_sha256":"$_a$_a"},"result":{"schema":"flywheel.gateway-operation-result/v1","operation_ref":"op_$_a","action":"agent.run","state":"completed","result":{"final":"done"}}}\r\n\r\nid: 2\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n';

typedef _Harness = ({
  CodeBufferSession session,
  GatewayOperationController controller,
  Completer<void>? prepareGate,
  List<String> calls,
  List<Map<String, dynamic>> sent,
  String root,
});

Directory _temporary(String name) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

Map<String, Object?> _proposal(GatewayOperation operation) {
  final shared = <String, Object?>{
    'action': operation.action,
    'journey_ref': _binding.journeyRef,
    'expected_event_head': _binding.eventHead,
    'destination': operation.destination.toJson(),
    'tool': operation.tool,
    'operation_sha256': _binding.eventHead,
    'arguments_sha256': _binding.eventHead,
    'scopes': operation.scopes,
    'data_refs': operation.dataRefs,
    'credential_refs': operation.credentialRefs,
    'expires_at': '2026-08-15T12:02:00Z',
  };
  return {
    'schema': 'flywheel.gateway-grant-proposal/v1',
    'proposal_ref': 'prp_$_a',
    'planned_grant_ref': 'gnt_$_a',
    ...shared,
    'client_request_id': operation.clientRequestId,
    'summary': {
      'schema': 'flywheel.gateway-grant-summary/v1',
      ...shared,
      'effect': 'one dispatch after approval',
    }
  };
}

Future<_Harness> _mountCodeView(WidgetTester tester,
    {bool holdPrepare = false, bool twoFiles = false}) async {
  await tester.binding.setSurfaceSize(const Size(1400, 1000));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final directory = _temporary('code-agent-context-');
  final root = Directory('${directory.path}/workspace')..createSync();
  final first = File('${root.path}/lib/a.dart')
    ..createSync(recursive: true)
    ..writeAsStringSync('selected value');
  final session = CodeBufferSession(
      draftStore: CodeDraftStore(root: Directory('${directory.path}/drafts')))
    ..openWorkspace(root.path)
    ..recover()
    ..openFile(first.path);
  if (twoFiles) {
    final second = File('${root.path}/lib/b.dart')
      ..writeAsStringSync('selected value');
    session.openFile(second.path);
    session.openFiles.last.controller.selection =
        const TextSelection(baseOffset: 0, extentOffset: 8);
    session.selectIndex(0);
  }
  session.openFiles.first.controller.selection =
      const TextSelection(baseOffset: 0, extentOffset: 8);
  final gate = holdPrepare ? Completer<void>() : null;
  final calls = <String>[];
  final sent = <Map<String, dynamic>>[];
  late GatewayOperation captured;
  final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(_roster, 200);
        }
        if (request.url.path.contains('/prepare/')) {
          calls.add('prepare');
          if (gate != null) await gate.future;
          return http.Response(jsonEncode(_proposal(captured)), 200);
        }
        if (request.url.path.endsWith('/approve-once')) {
          calls.add('approve');
          return http.Response(jsonEncode(_approval), 200);
        }
        calls.add('dispatch');
        sent.add(jsonDecode(request.body) as Map<String, dynamic>);
        return http.Response(_operationDone, 200);
      }));
  final controller = GatewayOperationController(GatewayGrantClient(client));
  await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
          authorize: (context, operation, current, dispatch) async {
            captured = operation;
            final ready = await controller.prepare(operation,
                binding: _binding,
                currentOperation: current,
                currentBinding: () => _binding);
            if (!context.mounted || !ready) return null;
            return showOperationGrantSheet<Object?>(
                context, controller, dispatch);
          },
          child: Scaffold(
              body: CodeView(
                  client: client,
                  alive: true,
                  settings: DesktopSettings(),
                  session: session,
                  guard: UnsavedWorkGuard(
                      session: session,
                      prompt: (_) async => CloseChoice.cancel))))));
  await tester.pumpAndSettle();
  return (
    session: session,
    controller: controller,
    prepareGate: gate,
    calls: calls,
    sent: sent,
    root: root.path
  );
}

Future<void> _startRun(WidgetTester tester) async {
  await tester.enterText(find.byType(TextField).last, 'inspect');
  await tester.tap(find.text('Run'));
  await tester.pump();
}

Future<void> _selectEditor(
    WidgetTester tester, CodeBufferSession session, int start, int end) async {
  final controller = session.openFiles[session.activeIndex].controller;
  final editor = find.byWidgetPredicate(
      (widget) => widget is TextField && widget.controller == controller);
  expect(editor, findsOneWidget);
  tester.widget<TextField>(editor).controller!.selection =
      TextSelection(baseOffset: start, extentOffset: end);
  await tester.pump();
}

void main() {
  _selectionLifetimeTests();
  _invalidationNodeTests();
  _invalidPathTests();
}

void _selectionLifetimeTests() {
  testWidgets('code view authorizes structured relative attachment',
      (tester) async {
    final harness = await _mountCodeView(tester);
    await _startRun(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();
    expect(harness.sent.single['attachment'],
        {'relative_path': 'lib/a.dart', 'selection': 'selected'});
    expect(harness.sent.single['goal'], 'inspect');
    expect(jsonEncode(harness.sent), isNot(contains(harness.root)));
  });

  testWidgets('selection-only change during prepare prevents approval',
      (tester) async {
    final harness = await _mountCodeView(tester, holdPrepare: true);
    await _startRun(tester);
    await _selectEditor(tester, harness.session, 9, 14);
    harness.prepareGate!.complete();
    await tester.pumpAndSettle();
    expect(harness.controller.failure?.code, 'OPERATION_CHANGED');
    expect(harness.calls, ['prepare']);
    expect(harness.sent, isEmpty);
  });

  testWidgets('selection-only change during approval prevents approval',
      (tester) async {
    final harness = await _mountCodeView(tester);
    await _startRun(tester);
    await tester.pumpAndSettle();
    await _selectEditor(tester, harness.session, 9, 14);
    await tester.tap(find.text('Approve once'));
    await tester.pump();
    expect(harness.controller.failure?.code, 'OPERATION_CHANGED');
    expect(harness.calls, ['prepare']);
    expect(harness.sent, isEmpty);
  });
}

void _invalidationNodeTests() {
  testWidgets('attach toggle independently invalidates prepare',
      (tester) async {
    final harness = await _mountCodeView(tester, holdPrepare: true);
    await _startRun(tester);
    await tester.tap(find.byType(Checkbox).last);
    await tester.pump();
    harness.prepareGate!.complete();
    await tester.pumpAndSettle();
    expect(harness.controller.failure?.code, 'OPERATION_CHANGED');
    expect(harness.calls, ['prepare']);
  });

  testWidgets('active file change independently invalidates prepare',
      (tester) async {
    final harness =
        await _mountCodeView(tester, holdPrepare: true, twoFiles: true);
    await _startRun(tester);
    harness.session.selectIndex(1);
    await tester.pump();
    harness.prepareGate!.complete();
    await tester.pumpAndSettle();
    expect(harness.controller.failure?.code, 'OPERATION_CHANGED');
    expect(harness.calls, ['prepare']);
  });
}

void _invalidPathTests() {
  testWidgets('invalid local attachment shapes stop before authorization',
      (tester) async {
    var prepares = 0, approvals = 0, dispatches = 0;
    final client = GatewayClient(
        baseUrl: 'https://agent.invalid',
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/endpoints') {
            return http.Response(_roster, 200);
          }
          dispatches++;
          return http.Response(_operationDone, 200);
        }));
    for (final path in [
      r'lib\main.dart',
      '../main.dart',
      'lib/../main.dart',
      '%2e%2e/main.dart',
      '%252e%252e/main.dart',
      '%25252e%25252e/main.dart',
      r'C:\private\main.dart',
      'C:/private/main.dart',
      'C:main.dart',
      '/private/main.dart',
      r'\rooted\main.dart',
    ]) {
      await tester.pumpWidget(MaterialApp(
          theme: flywheelLightTheme(),
          home: GatewayOperationScope(
              authorize: (_, operation, __, dispatch) async {
                prepares++;
                approvals++;
                return dispatch(operation.finalBody(_binding, 'gnt_$_a'));
              },
              child: Scaffold(
                  body: AgentPanel(
                      key: ValueKey(path),
                      client: client,
                      alive: true,
                      workspaceRoot: 'workspace',
                      activeFile: path,
                      onRunStarted: () {},
                      onRunFinished: () {})))));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'inspect');
      await tester.tap(find.text('Run'));
      await tester.pumpAndSettle();
      expect(find.text('The run failed: INVALID_CONTEXT'), findsOneWidget,
          reason: path);
      expect((prepares, approvals, dispatches), (0, 0, 0), reason: path);
    }
  });
}

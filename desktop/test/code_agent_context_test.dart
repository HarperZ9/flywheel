import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/ide/agent_panel.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/code_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', '$_a$_a');
const _roster =
    '{"rows":[{"name":"local-public","backend":"local","credential":"local-none","provider_role":"","configured":true}]}';

Directory _temporary(String name) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

void main() {
  testWidgets('code view authorizes structured relative attachment on Windows',
      (tester) async {
    if (!Platform.isWindows) markTestSkipped('Windows absolute-path fixture');
    await tester.binding.setSurfaceSize(const Size(1400, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final directory = _temporary('code-agent-context-');
    final root = Directory('${directory.path}/workspace')..createSync();
    final file = File('${root.path}/lib/main.dart')
      ..createSync(recursive: true)
      ..writeAsStringSync('selected value');
    final session = CodeBufferSession(
        draftStore: CodeDraftStore(root: Directory('${directory.path}/drafts')))
      ..openWorkspace(root.path)
      ..recover()
      ..openFile(file.path);
    session.openFiles.single.controller.selection =
        const TextSelection(baseOffset: 0, extentOffset: 8);
    Map<String, dynamic>? sent;
    final client = GatewayClient(
        baseUrl: 'https://agent.invalid',
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/endpoints') {
            return http.Response(_roster, 200);
          }
          sent = jsonDecode(request.body);
          return http.Response('data: [DONE]\n\n', 200);
        }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: GatewayOperationScope(
            authorize: (_, operation, current, dispatch) =>
                current() != operation
                    ? Future.value()
                    : dispatch(operation.finalBody(_binding, 'gnt_$_a')),
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
    await tester.enterText(find.byType(TextField).last, 'inspect');
    await tester.tap(find.text('Run'));
    await tester.pumpAndSettle();
    expect(sent, isNotNull);
    expect(sent!['attachment'],
        {'relative_path': 'lib/main.dart', 'selection': 'selected'});
    expect(sent!['goal'], 'inspect');
    expect(jsonEncode(sent), isNot(contains(root.path)));
  });

  testWidgets('unsafe attached context reports fixed invalid context',
      (tester) async {
    final client = GatewayClient(
        baseUrl: 'https://agent.invalid',
        httpClient: MockClient((_) async => http.Response(_roster, 200)));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: GatewayOperationScope(
            authorize: (_, __, ___, ____) => Future.value(),
            child: Scaffold(
                body: AgentPanel(
                    client: client,
                    alive: true,
                    workspaceRoot: 'workspace',
                    activeFile: r'C:\private\main.dart',
                    onRunStarted: () {},
                    onRunFinished: () {})))));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'inspect');
    await tester.tap(find.text('Run'));
    await tester.pump();
    expect(find.text('The run failed: INVALID_CONTEXT'), findsOneWidget);
  });
}

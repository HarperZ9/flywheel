import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/usage_live_selection.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/widgets/chat_header.dart';

void main() {
  testWidgets('chat publishes endpoint selection and its own model override',
      (tester) async {
    final directory = Directory.systemTemp.createTempSync('usage-selection-');
    final selection = UsageLiveSelectionController();
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.url.path == '/api/endpoints') {
        return http.Response(jsonEncode({'rows': [
          {'name': 'llamacpp', 'credential': 'local-none', 'configured': true},
          {'name': 'vllm', 'credential': 'local-none', 'configured': true},
        ]}), 200);
      }
      return http.Response('{}', 200);
    }));
    addTearDown(() {
      client.close();
      selection.dispose();
      directory.deleteSync(recursive: true);
    });
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: AgentView(
        client: client, alive: true, settings: DesktopSettings(),
        chatStore: ChatStore(file: File('${directory.path}/history.json')),
        draftStore: ChatDraftStore(file: File('${directory.path}/drafts.json')),
        usageSelection: selection,
      )),
    ));
    await tester.pumpAndSettle();
    expect(selection.value.endpoint, 'llamacpp');
    ChatHeader header() => tester.widget<ChatHeader>(find.byType(ChatHeader));
    header().onModel('local-a');
    await tester.pump();
    expect(selection.value.path, '/api/usage/live?endpoint=llamacpp&model=local-a');
    header().onEndpoint('vllm');
    await tester.pump();
    expect(selection.value.path, '/api/usage/live?endpoint=vllm');
    header().onModel('local-b');
    await tester.pump();
    expect(selection.value.model, 'local-b');
    header().onEndpoint('llamacpp');
    await tester.pump();
    expect(selection.value.model, 'local-a');
    header().onModel('');
    await tester.pump();
    expect(selection.value.path, '/api/usage/live?endpoint=llamacpp');
    await tester.pumpWidget(const SizedBox());
  });
}

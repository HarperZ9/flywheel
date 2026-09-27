// plugin_call_wait_test.dart - the Plugins tool call waits longer than the
// engine does (WP9b). The engine gives a plugin tool 45 s
// (harness/plugins.py call_plugin); the app used to stop at 15 s and report a
// transport failure for a call the engine was still running.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/tool_spec.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/tool_call_sheet.dart';

void main() {
  testWidgets('a plugin call answered after 40 s still reaches the sheet',
      (tester) async {
    final client = GatewayClient(
        baseUrl: 'http://engine.invalid',
        httpClient: MockClient((request) async {
          await Future<void>.delayed(const Duration(seconds: 40));
          return http.Response(jsonEncode({'answer': 'late but real'}), 200);
        }));
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: (context, operation, current, dispatch) =>
            dispatch({...operation.operation, 'grant_ref': 'gnt_test'}),
        child: Scaffold(
          body: SingleChildScrollView(
            child: ToolCallSheet(
                client: client,
                plugin: 'gather',
                spec: const ToolSpec(name: 'gather.status'),
                credentialRefs: const []),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('Call'));
    await tester.pump(const Duration(seconds: 41));
    expect(find.textContaining('late but real'), findsOneWidget);
    expect(pluginCallWait, greaterThan(const Duration(seconds: 45)));
  });
}

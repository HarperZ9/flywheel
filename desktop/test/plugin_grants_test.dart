import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/tool_spec.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/plugins_view.dart';
import 'package:flywheel_desktop/widgets/plugin_forms.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:flywheel_desktop/widgets/tool_call_sheet.dart';

Widget _authorized(Widget child, GatewayOperationAuthorizer authorize) =>
    MaterialApp(
        theme: flywheelLightTheme(),
        home: GatewayOperationScope(
            authorize: authorize, child: Scaffold(body: child)));

GatewayClient _client() => GatewayClient(
    baseUrl: 'https://plugins.invalid',
    httpClient: MockClient((_) async => http.Response(
        '{"plugins":[],"entries":[],"rows":[],"summary":'
        '{"witnessed":0,"uniquely_witnessed":[],"gaps":[]}}',
        200)));

void main() {
  _operationModelTest();
  _neutralStatusTest();
  _rawEditTest();
  _registerEditTest();
}

void _operationModelTest() {
  test('plugin operations snapshot nested arguments and reject secret input',
      () {
    final nested = <String, dynamic>{
      'items': [
        <String, dynamic>{'v': 'old'}
      ]
    };
    final operation = GatewayOperation.pluginCall(
        name: 'custom',
        tool: 'run',
        arguments: nested,
        credentialRefs: const [],
        clientRequestId: 'request-1');
    (nested['items'] as List).first['v'] = 'new';
    expect(operation.operation['arguments'], {
      'items': [
        {'v': 'old'}
      ]
    });
    expect(
        () => GatewayOperation.pluginCall(
            name: 'custom',
            tool: 'run',
            arguments: const {'api_key': 'raw-secret'},
            credentialRefs: const [],
            clientRequestId: 'request-2'),
        throwsArgumentError);
  });
}

void _neutralStatusTest() {
  testWidgets('plugin live and enabled remain neutral present unchecked',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: const Scaffold(
          body: ProbeResult(probe: {
        'status': 'live',
        'tool_specs': <Object>[],
      })),
    ));
    final text = tester
        .widgetList<Text>(find.byType(Text))
        .map((widget) => widget.data ?? '')
        .join(' ');
    expect(text.toLowerCase(), contains('live'));
    expect(text.toLowerCase(), isNot(contains('verified')));
    expect(text, isNot(contains('MATCH')));
    expect(tester.widget<VerdictPill>(find.byType(VerdictPill)).status,
        'present_unchecked');
    expect(
        find.bySemanticsLabel('Live reported; not verified'), findsOneWidget);
  });
}

void _rawEditTest() {
  testWidgets('editing raw tool arguments invalidates pending authorization',
      (tester) async {
    final pending = Completer<Object?>();
    late GatewayOperation captured;
    late GatewayOperationSupplier current;
    await tester.pumpWidget(_authorized(
        ToolCallSheet(
            client: _client(),
            plugin: 'gather',
            spec: const ToolSpec(name: 'query'),
            credentialRefs: const []), (_, operation, supplier, dispatch) {
      captured = operation;
      current = supplier;
      return pending.future;
    }));
    await tester.tap(find.text('RAW JSON'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), '{"q":"old"}');
    await tester.tap(find.text('Call'));
    await tester.pump();
    expect(current(), captured);
    await tester.enterText(find.byType(TextField), '{"q":"new"}');
    expect(current(), isNot(captured));
    pending.complete();
    await tester.pump();
  });
}

void _registerEditTest() {
  testWidgets('editing register fields invalidates pending authorization',
      (tester) async {
    final pending = Completer<Object?>();
    late GatewayOperation captured;
    late GatewayOperationSupplier current;
    await tester.pumpWidget(
        _authorized(PluginsView(client: _client(), alive: true),
            (_, operation, supplier, dispatch) {
      captured = operation;
      current = supplier;
      return pending.future;
    }));
    await tester.pump();
    await tester.enterText(find.byType(TextField).at(0), 'gather');
    await tester.enterText(find.byType(TextField).at(1), 'gather mcp');
    await tester.tap(find.text('Register'));
    await tester.pump();
    expect(current(), captured);
    await tester.enterText(find.byType(TextField).at(0), 'forum');
    expect(current(), isNot(captured));
    pending.complete();
    await tester.pump();
  });
}

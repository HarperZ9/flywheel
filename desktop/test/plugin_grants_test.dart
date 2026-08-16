import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/plugin_forms.dart';

void main() {
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
  });
}

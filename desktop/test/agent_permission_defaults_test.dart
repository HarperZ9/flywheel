import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/ide/agent_panel.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

void main() {
  testWidgets('agent write and exec permissions both default false',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: AgentPanel(
                client: GatewayClient(),
                alive: false,
                workspaceRoot: r'C:\workspace',
                onRunStarted: () {},
                onRunFinished: () {}))));

    final values = tester
        .widgetList<Checkbox>(find.byType(Checkbox))
        .map((checkbox) => checkbox.value)
        .toList();
    expect(values, [false, false, true]);
  });

  test('agent panel has no observational detach or leave-running control', () {
    final source = File('lib/ide/agent_panel.dart').readAsStringSync();
    expect(source.contains('_detached'), isFalse);
    expect(source.contains('Detach'), isFalse);
    expect(source.contains('Leave running'), isFalse);
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/ide/agent_gates.dart';
import 'package:flywheel_desktop/models/agent_tool_protocol.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/effort_dial.dart';

void main() {
  testWidgets('subscription routes name account state instead of no key',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: AgentGates(
          endpoints: [
            EndpointRow.fromJson({
              'name': 'codex-cli',
              'backend': 'cli',
              'credential': 'cli-auth',
              'account_authenticated': true,
              'account_state': 'authenticated',
              'route_ready': false,
              'route_ready_reason': 'not_checked',
            }),
          ],
          endpoint: 'codex-cli',
          model: null,
          allowWrite: false,
          allowExec: false,
          attachContext: false,
          toolProtocol: AgentToolProtocol.compatibility,
          onEndpoint: (_) {},
          onModel: (_) {},
          onToolProtocol: (_) {},
          loadModels: () async => const {'models': []},
          onWrite: (_) {},
          onExec: (_) {},
          onAttach: (_) {},
          effort: EffortLevel.standard,
          onEffort: (_) {},
        ),
      ),
    ));

    expect(
        find.text('codex-cli (connected; run check needed)'), findsOneWidget);
    expect(find.textContaining('no key'), findsNothing);
  });
}

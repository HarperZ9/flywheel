// The run budget fields send what they show.
//
// A typed limit reaches the approved operation without Enter, a value the
// engine would refuse is named under its field and blocks the run, a stored
// sub-cent limit is shown exactly, the defaults and the check-command
// explanation are visible at rest, and neither field drops an MCP admission.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/rowan_run_budget.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_operation_budget.dart';

const _actions = Key('assistant-rowan-max-tool-actions');
const _tokens = Key('assistant-rowan-max-usage-tokens');
const _cost = Key('assistant-rowan-max-cost');

final class _Host {
  _Host(this.rowan);
  final RowanOperationController rowan;
  late BuildContext context;
  Map<String, Object?>? approved;
  var authorizations = 0;
}

Future<_Host> _pump(WidgetTester tester, RowanOperationController rowan,
    {bool open = true}) async {
  final host = _Host(rowan);
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: GatewayOperationScope(
      authorize: (_, operation, supplier, dispatch) async {
        host.authorizations++;
        host.approved = operation.operation;
        return const GatewayAuthorizationOutcome<bool>.denied();
      },
      child: Builder(builder: (ctx) {
        host.context = ctx;
        return Scaffold(
          body: ListenableBuilder(
            listenable: rowan,
            builder: (_, __) => Column(children: [
              // Closing the panel disposes the row; reopening builds a new one.
              if (open) RowanRunBudgetRow(rowan: rowan),
              RowanCheckCommandField(rowan: rowan),
              const TextField(key: Key('elsewhere')),
            ]),
          ),
        );
      }),
    ),
  ));
  return host;
}

RowanOperationController _rowan() {
  final rowan = RowanOperationController(GatewayClient())..setEndpoint('local');
  addTearDown(rowan.dispose);
  return rowan;
}

/// Whether nothing above the finder hides it: no zero opacity or fade.
bool _shown(WidgetTester tester, Finder finder) {
  var visible = true;
  tester.element(finder).visitAncestorElements((ancestor) {
    final w = ancestor.widget;
    if (w is AnimatedOpacity && w.opacity == 0 ||
        w is Opacity && w.opacity == 0 ||
        w is FadeTransition && w.opacity.value == 0) {
      visible = false;
    }
    return visible;
  });
  return visible;
}

void main() {
  testWidgets('a typed limit reaches the run without Enter', (tester) async {
    final host = await _pump(tester, _rowan());
    await tester.enterText(find.byKey(_actions), '3');
    await tester.enterText(find.byKey(_cost), '0.10');
    await tester.tap(find.byKey(const Key('elsewhere')));
    await tester.pump();
    await host.rowan.start(host.context, 'inspect');
    expect(host.approved?['run_budget'],
        {'max_tool_actions': 3, 'max_cost_micros': 100000});

    // Clearing the fields goes back to the engine defaults.
    await tester.enterText(find.byKey(_actions), '');
    await tester.enterText(find.byKey(_cost), '');
    await host.rowan.start(host.context, 'inspect');
    expect(host.approved?.containsKey('run_budget'), isFalse);
  });

  testWidgets('a value the engine would refuse is named and blocks the run',
      (tester) async {
    final host = await _pump(tester, _rowan());
    await tester.enterText(find.byKey(_actions), '3');
    await tester.enterText(find.byKey(_actions), '500');
    await tester.pump();
    expect(find.text('tool actions: 0 to 200'), findsOneWidget);
    // An unrelated setter does not clear the refusal.
    host.rowan.setCheckCommand('pytest');
    final outcome = await host.rowan.start(host.context, 'inspect');
    expect(outcome.failure?.code, 'INVALID_RUN_BUDGET');
    expect(host.authorizations, 0);
    expect(host.rowan.error, 'INVALID_RUN_BUDGET');

    await tester.enterText(find.byKey(_actions), 'abc');
    await tester.pump();
    expect(find.text('tool actions: 0 to 200'), findsOneWidget);

    // Fixing it lifts the block, and the comma form the card prints is read.
    await tester.enterText(find.byKey(_actions), '');
    await tester.enterText(find.byKey(_tokens), '200,000');
    await tester.pump();
    expect(find.textContaining('0 to 200'), findsNothing);
    await host.rowan.start(host.context, 'inspect');
    expect(host.authorizations, 1);
    expect(host.approved?['run_budget'], {'max_usage_tokens': 200000});
  });

  testWidgets('a reopened panel shows the text that blocks the run',
      (tester) async {
    final rowan = _rowan();
    var host = await _pump(tester, rowan);
    await tester.enterText(find.byKey(_actions), '500');
    await tester.enterText(find.byKey(_cost), 'ten');
    await _pump(tester, rowan, open: false);
    host = await _pump(tester, rowan);
    String typed(Key key) =>
        tester.widget<TextField>(find.byKey(key)).controller!.text;
    expect(typed(_actions), '500');
    expect(typed(_cost), 'ten');
    expect(find.text('tool actions: 0 to 200'), findsOneWidget);
    expect(find.text(r'spend: $0.01 to $1000.00'), findsOneWidget);
    final outcome = await host.rowan.start(host.context, 'inspect');
    expect(outcome.failure?.code, 'INVALID_RUN_BUDGET');
    expect(host.authorizations, 0);

    // Once fixed, a reopened panel shows the valid limit and runs under it.
    await tester.enterText(find.byKey(_actions), '7');
    await tester.enterText(find.byKey(_cost), '');
    await _pump(tester, rowan, open: false);
    host = await _pump(tester, rowan);
    expect(typed(_actions), '7');
    expect(find.text('tool actions: 0 to 200'), findsNothing);
    expect(find.textContaining('spend: '), findsNothing);
    expect(rowan.invalidRunBudgetField, isNull);
    await host.rowan.start(host.context, 'inspect');
    expect(host.approved?['run_budget'], {'max_tool_actions': 7});
  });

  testWidgets('a stored sub-cent spend limit is shown and kept exactly',
      (tester) async {
    final rowan = _rowan()
      ..setRunBudget(const RowanRunBudget(maxCostMicros: 15000));
    await _pump(tester, rowan);
    expect(
        tester.widget<TextField>(find.byKey(_cost)).controller!.text, '0.015');
    await tester.enterText(find.byKey(_actions), '5');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(rowan.runBudget.maxCostMicros, 15000);
    expect(dollarsFromMicros(2000000), '2.00');
    expect(dollarsFromMicros(10000), '0.01');
    expect(dollarsFromMicros(1234567), '1.234567');
  });

  testWidgets('defaults and the check explanation show at rest',
      (tester) async {
    final rowan = _rowan();
    await _pump(tester, rowan);
    expect(_shown(tester, find.text('24')), isTrue);
    expect(_shown(tester, find.text('200,000')), isTrue);
    const help =
        'allow exec to run a check; without one the answer stays claimed';
    expect(find.text(help), findsOneWidget);
    expect(_shown(tester, find.text(help)), isTrue);

    // A command typed while exec was on says it will not run once exec is off.
    rowan.setAllowExec(true);
    await tester.pump();
    await tester.enterText(
        find.byKey(const Key('assistant-rowan-check-command')), 'pytest -q');
    rowan.setAllowExec(false);
    await tester.pump();
    expect(find.text('exec is off: this check will not run'), findsOneWidget);
  });

  test('the budget and the check command keep an admitted MCP tool', () {
    final rowan = RowanOperationController(GatewayClient())
      ..setEndpoint('openai');
    addTearDown(rowan.dispose);
    const admission = {
      'schema': 'flywheel.agent-run-mcp-admission-request/v1',
      'servers': [
        {
          'server_id': 'index',
          'catalog_ref': 'index',
          'receipt_sha256':
              'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'tools': ['index.doctor'],
          'timeout_s': 10,
        },
      ],
    };
    rowan.setMcpAdmission(admission);
    rowan.setCheckCommand('p');
    expect(rowan.mcpAdmission, admission);
    rowan.setRunBudget(const RowanRunBudget(maxToolActions: 5));
    expect(rowan.mcpAdmission, admission);
    rowan.setWorkspaceRoot('C:/elsewhere');
    expect(rowan.mcpAdmission, isNull);
  });
}

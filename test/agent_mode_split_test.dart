// The Chat destination's agent mode and the shared resizable split: the
// header chips swap the chat surface for the gated tool loop, and compare's
// two panes sit on a real draggable divider whose fraction persists.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/views/compare_view.dart';

Future<void> _pump(WidgetTester tester, Widget child) => tester.pumpWidget(
    MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: child)));

void main() {
  test('a dragged split fraction is stored and read back, with a fallback', () {
    final s = DesktopSettings();
    expect(s.splitFraction('compare', 0.5), 0.5);
    s.setSplitFraction('compare', 0.62);
    expect(s.splitFraction('compare', 0.5), 0.62);
    expect(s.splitFraction('agent', 0.7), 0.7); // untouched views keep theirs
    s.cancelPendingSaves(); // the test never writes the real home dir
  });

  testWidgets('the agent chip swaps chat for the tool loop and back',
      (tester) async {
    await _pump(
        tester,
        AgentView(
            client: GatewayClient(),
            alive: true,
            settings: DesktopSettings()));
    await tester.pump();
    // chat mode: the tool loop is absent, the witness line names the chat
    expect(find.text('Point the agent at a workspace'), findsNothing);
    expect(find.text('every reply is witnessed'), findsOneWidget);

    await tester.tap(find.text('agent'));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsOneWidget);
    expect(find.text('every run persists with its trace'), findsOneWidget);

    await tester.tap(find.text('chat'));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsNothing);
    expect(find.text('every reply is witnessed'), findsOneWidget);
  });

  testWidgets('compare panes sit on a draggable divider', (tester) async {
    await _pump(
        tester,
        CompareView(
            client: GatewayClient(),
            alive: true,
            settings: DesktopSettings()));
    await tester.pump();
    expect(find.byKey(const Key('split-divider')), findsOneWidget);
    expect(find.text('Pick a model and send a prompt.'), findsNWidgets(2));
  });
}

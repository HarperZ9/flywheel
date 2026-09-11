import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/shell_rail.dart';

Widget _rail({
  bool collapsed = false,
  VoidCallback? onOpenRecovery,
  VoidCallback? onOpenConnection,
}) =>
    MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SizedBox(
          width: collapsed ? 52 : 260,
          height: 720,
          child: ShellRail(
            collapsed: collapsed,
            width: 240,
            selected: DestinationId.journey,
            onGo: (_) {},
            onResize: (_) {},
            onToggleCollapse: () {},
            onToggleTheme: () {},
            onOpenAppearance: () {},
            onOpenRecovery: onOpenRecovery ?? () {},
            onOpenConnection: onOpenConnection,
          ),
        ),
      ),
    );

void main() {
  testWidgets('rail search accepts workflow terms, not only exact labels', (
    tester,
  ) async {
    await tester.pumpWidget(_rail());
    final search = find.byType(TextField);

    await tester.enterText(search, 'assistant');
    await tester.pump();
    expect(find.text('Rowan'), findsOneWidget);

    await tester.enterText(search, 'connect');
    await tester.pump();
    expect(find.text('Models'), findsOneWidget);

    await tester.enterText(search, 'workspace');
    await tester.pump();
    expect(find.text('Projects'), findsOneWidget);

    await tester.enterText(search, 'capabilities');
    await tester.pump();
    expect(find.text('Tools'), findsOneWidget);

    await tester.enterText(search, 'marketplace');
    await tester.pump();
    expect(find.text('Plugins'), findsOneWidget);
  });

  testWidgets('collapsed rail exposes recovery and connection actions', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    var recovery = 0;
    var connection = 0;

    await tester.pumpWidget(
      _rail(
        collapsed: true,
        onOpenRecovery: () => recovery++,
        onOpenConnection: () => connection++,
      ),
    );

    final recoveryAction = find.bySemanticsLabel('Open recovery center');
    final connectionAction = find.bySemanticsLabel('Pair a gateway connection');
    expect(recoveryAction, findsOneWidget);
    expect(connectionAction, findsOneWidget);

    await tester.tap(recoveryAction);
    await tester.tap(connectionAction);
    expect(recovery, 1);
    expect(connection, 1);
    semantics.dispose();
  });
}

// On a phone the engine runs on the paired computer, so the surfaces that
// tell a desktop user to run a shell command or start a local engine tell a
// phone user where the engine lives instead. Both branches are exercised with
// an explicit flag, never the ambient test platform.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:flywheel_desktop/widgets/status_bar.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

void main() {
  testWidgets('FwEmpty on desktop shows the command; a phone shows pairing',
      (tester) async {
    await tester.pumpWidget(_wrap(
        const FwEmpty('Engine offline.', command: 'flywheel up', mobile: false)));
    expect(find.text('flywheel up'), findsOneWidget);
    expect(find.textContaining('Pair it from Connection'), findsNothing);

    await tester.pumpWidget(_wrap(
        const FwEmpty('Engine offline.', command: 'flywheel up', mobile: true)));
    expect(find.text('flywheel up'), findsNothing,
        reason: 'a phone has no terminal to run it in');
    expect(find.textContaining('Pair it from Connection'), findsOneWidget);
  });

  testWidgets('FwEmpty with no command shows neither affordance',
      (tester) async {
    await tester
        .pumpWidget(_wrap(const FwEmpty('Nothing yet.', mobile: true)));
    expect(find.text('flywheel up'), findsNothing);
    expect(find.textContaining('Pair it from Connection'), findsNothing);
  });

  testWidgets('StatusBar offers Start engine on desktop, not on a phone',
      (tester) async {
    StatusBar bar({required bool local}) => StatusBar(
          alive: false,
          message: 'engine offline',
          startError: null,
          world: null,
          onStartEngine: () {},
          local: local,
        );

    await tester.pumpWidget(_wrap(bar(local: true)));
    expect(find.text('start engine'), findsOneWidget);
    expect(find.text('on your computer'), findsNothing);

    await tester.pumpWidget(_wrap(bar(local: false)));
    expect(find.text('start engine'), findsNothing,
        reason: 'a phone cannot start the engine locally');
    expect(find.text('on your computer'), findsOneWidget);
  });

  testWidgets('a live StatusBar shows no start action on either device',
      (tester) async {
    for (final local in const [true, false]) {
      await tester.pumpWidget(_wrap(StatusBar(
        alive: true,
        message: '5/5 lanes live',
        startError: null,
        world: null,
        onStartEngine: () {},
        local: local,
      )));
      expect(find.text('start engine'), findsNothing);
      expect(find.text('on your computer'), findsNothing);
    }
  });
}

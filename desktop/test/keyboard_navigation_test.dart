// Keyboard navigation: the palette shortcut, the composer's Enter-to-send
// with Shift+Enter newline, and the rail resizer's arrow adjustment are
// the shell's three global keyboard contracts.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/command_palette.dart';
import 'package:flywheel_desktop/widgets/rail_resizer.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

void main() {
  testWidgets('Ctrl+K opens the palette; Escape closes without navigating',
      (tester) async {
    final opened = <DestinationId>[];
    await tester.pumpWidget(_wrap(PaletteShortcuts(
      onGo: opened.add,
      child: const Focus(autofocus: true, child: SizedBox.expand()),
    )));
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyDownEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();
    expect(find.text('Go to…'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text('Go to…'), findsNothing);
    expect(opened, isEmpty);
  });

  testWidgets('the rail resizer responds to Home and End bounds',
      (tester) async {
    double? width;
    await tester.pumpWidget(_wrap(SizedBox(
      width: 200,
      child: Stack(children: [
        Positioned(
          right: 0,
          top: 0,
          bottom: 0,
          width: 6,
          child: RailResizer(width: 200, onResize: (w) => width = w),
        ),
      ]),
    )));
    await tester.pump();
    final focus = tester.state(
        find.byKey(const Key('rail-resizer-focus'))) as dynamic;
    focus.focusNode.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(width, 216);
    await tester.sendKeyEvent(LogicalKeyboardKey.end);
    await tester.pump();
    expect(width, 320);
    await tester.sendKeyEvent(LogicalKeyboardKey.home);
    await tester.pump();
    expect(width, 148);
  });
}

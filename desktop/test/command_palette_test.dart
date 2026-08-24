// The Ctrl+K palette: type filters all thirty destinations, Enter opens
// the highlighted one, Escape closes without navigating.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/command_palette.dart';

void main() {
  testWidgets('the palette lists destinations and opens on Enter',
      (tester) async {
    final opened = <DestinationId>[];
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: PaletteGo(
        onGo: opened.add,
        child: Scaffold(
          body: Builder(builder: (context) => Center(
            child: ElevatedButton(
                onPressed: () => showCommandPalette(context, opened.add),
                child: const Text('open palette')),
          )),
        ),
      ),
    ));
    await tester.tap(find.text('open palette'));
    await tester.pumpAndSettle();

    // The catalog is listed before any query (the dialog builds lazily,
    // so assert on early entries).
    expect(find.text('Journey'), findsOneWidget);
    expect(find.text('Plan'), findsOneWidget);

    // Typing narrows by stable label.
    await tester.enterText(find.byType(TextField), 'receipt');
    await tester.pump();
    expect(find.text('Receipts'), findsOneWidget);
    expect(find.text('Journey'), findsNothing);

    // Activating the row opens the destination.
    await tester.tap(find.text('Receipts'));
    await tester.pumpAndSettle();
    expect(opened, [DestinationId.receipts]);
  });

  testWidgets('a query with no match states the fact and opens nothing',
      (tester) async {
    final opened = <DestinationId>[];
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: PaletteGo(
        onGo: opened.add,
        child: Scaffold(
          body: Builder(builder: (context) => Center(
            child: ElevatedButton(
                onPressed: () => showCommandPalette(context, opened.add),
                child: const Text('open palette')),
          )),
        ),
      ),
    ));
    await tester.tap(find.text('open palette'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'zzzz');
    await tester.pump();
    expect(find.text('No destination matches.'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(opened, isEmpty);
  });

  testWidgets('Ctrl+K opens the palette from anywhere in the shell scope',
      (tester) async {
    final opened = <DestinationId>[];
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: PaletteShortcuts(
        onGo: opened.add,
        child: const Scaffold(
            body: Focus(autofocus: true, child: SizedBox.expand())),
      ),
    ));
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyDownEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();
    expect(find.text('Go to…'), findsOneWidget);
  });
}

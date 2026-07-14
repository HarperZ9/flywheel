// SplitPane: two panes, a draggable hairline divider, and hard minimum
// fractions — the checks that would prove the resizable chrome broken.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:flywheel_desktop/widgets/split_pane.dart';

Widget _host(Widget child) => MaterialApp(
    theme: flywheelLightTheme(),
    home: Scaffold(body: Center(child: SizedBox(width: 800, height: 600, child: child))));

void main() {
  testWidgets('SplitPane renders both panes and dragging resizes the first',
      (tester) async {
    await tester.pumpWidget(_host(SplitPane(
      axis: Axis.horizontal,
      initialFraction: 0.25,
      first: Container(key: const Key('a')),
      second: Container(key: const Key('b')),
    )));
    expect(find.byKey(const Key('a')), findsOneWidget);
    expect(find.byKey(const Key('b')), findsOneWidget);
    final before = tester.getSize(find.byKey(const Key('a'))).width;
    await tester.drag(find.byKey(const Key('split-divider')),
        const Offset(120, 0));
    await tester.pump();
    final after = tester.getSize(find.byKey(const Key('a'))).width;
    expect(after, greaterThan(before + 80));
  });

  testWidgets('SplitPane never shrinks a pane below its minimum fraction',
      (tester) async {
    await tester.pumpWidget(_host(SplitPane(
      axis: Axis.horizontal,
      initialFraction: 0.4,
      minFraction: 0.15,
      first: Container(key: const Key('a')),
      second: Container(key: const Key('b')),
    )));
    await tester.drag(find.byKey(const Key('split-divider')),
        const Offset(-700, 0));
    await tester.pump();
    final width = tester.getSize(find.byKey(const Key('a'))).width;
    expect(width, greaterThan(800 * 0.15 - 20));
  });

  testWidgets('AdaptiveTiles stacks below the breakpoint and rows above it',
      (tester) async {
    Widget tiles(double width) => MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: Center(
                child: SizedBox(
                    width: width,
                    child: AdaptiveTiles(children: [
                      Container(key: const Key('t0'), height: 40),
                      Container(key: const Key('t1'), height: 40),
                    ])))));
    await tester.pumpWidget(tiles(800));
    await tester.pump();
    expect(tester.getSize(find.byKey(const Key('t0'))).width, lessThan(450));
    await tester.pumpWidget(tiles(400));
    await tester.pump();
    expect(tester.getSize(find.byKey(const Key('t0'))).width,
        greaterThan(350));
  });
}

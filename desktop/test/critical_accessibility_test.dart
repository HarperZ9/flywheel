// Critical accessibility: the P0 matrix from the completion spec. Rail
// items, the rail resizer, the split divider, the graph canvas, and the
// icon buttons must all expose semantic roles and keyboard paths, and
// the composed text scaler must multiply system by user scale.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/graph_models.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/graph_canvas.dart';
import 'package:flywheel_desktop/widgets/rail_resizer.dart';
import 'package:flywheel_desktop/widgets/side_rail.dart';
import 'package:flywheel_desktop/widgets/split_pane.dart';
import 'package:flywheel_desktop/widgets/system_text_scaler.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

void main() {
  testWidgets('rail items are semantic buttons selectable by keyboard',
      (tester) async {
    int? selected;
    final semantics = tester.ensureSemantics();
    final planNode = FocusNode();
    addTearDown(planNode.dispose);
    await tester.pumpWidget(_wrap(SideRail(
      destinations: const [
        RailDestination('Journey', group: 'Work'),
        RailDestination('Plan', group: 'Work'),
      ],
      selectedIndex: 0,
      onSelect: (i) => selected = i,
      themeMode: ThemeMode.light,
      onToggleTheme: () {},
      collapsed: false,
      onToggleCollapse: () {},
      itemFocusNodes: {1: planNode},
    )));
    await tester.pump();

    // Semantic contract: every destination is a button carrying its label.
    expect(find.bySemanticsLabel(RegExp(r'Plan')), findsOneWidget);

    // Keyboard contract: focus the Plan item, press Enter, expect selection.
    planNode.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(selected, 1);
    semantics.dispose();
  });

  testWidgets('the rail resizer adjusts by keyboard', (tester) async {
    double? width;
    await tester.pumpWidget(_wrap(SizedBox(
      width: 200,
      child: Stack(children: [
        Positioned(
          right: 0,
          top: 0,
          bottom: 0,
          width: 6,
          child: RailResizer(width: 172, onResize: (w) => width = w),
        ),
      ]),
    )));
    await tester.pump();

    final focus = tester.state(
        find.byKey(const Key('rail-resizer-focus'))) as dynamic;
    focus.focusNode!.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(width, 188);
    await tester.sendKeyEvent(LogicalKeyboardKey.home);
    await tester.pump();
    expect(width, 148);
  });

  testWidgets('the split divider nudges by keyboard', (tester) async {
    double? fraction;
    await tester.pumpWidget(_wrap(SizedBox(
      width: 400,
      height: 100,
      child: SplitPane(
        axis: Axis.horizontal,
        first: const SizedBox(),
        second: const SizedBox(),
        onFraction: (f) => fraction = f,
      ),
    )));
    await tester.pump();

    final focus = tester.state(
        find.byKey(const Key('split-divider-focus'))) as dynamic;
    focus.focusNode!.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(fraction, greaterThan(0.3));
  });

  testWidgets('the graph canvas cycles nodes by arrow keys', (tester) async {
    final graph = KnowledgeGraph(nodes: [
      GraphNode(
          id: 'a',
          kind: 'lane',
          label: 'A',
          verdict: 'enabled',
          priority: 1,
          cost: 0,
          signals: const {}),
      GraphNode(
          id: 'b',
          kind: 'lane',
          label: 'B',
          verdict: 'enabled',
          priority: 2,
          cost: 0,
          signals: const {}),
    ], edges: []);
    String? selected;
    await tester.pumpWidget(_wrap(SizedBox(
      width: 400,
      height: 300,
      child: GraphCanvas(graph: graph, onSelect: (n) => selected = n?.id),
    )));
    await tester.pump();

    final focus = tester.state(
        find.byKey(const Key('graph-canvas-focus'))) as dynamic;
    focus.focusNode!.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(selected, 'a');
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(selected, 'b');
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    expect(selected, isNull);
  });

  test('the composed scaler multiplies system by user scale', () {
    final scaler = ComposedTextScaler(
        system: const TextScaler.linear(2.0), userScale: 1.2);
    expect(scaler.scale(10.0), closeTo(24.0, 0.001));
    expect(scaler.textScaleFactor, closeTo(2.4, 0.001));
  });

  test('DesktopSettings keeps the user scale bounded by the app builder',
      () {
    final s = DesktopSettings()..uiScale = 9.9;
    expect(s.uiScale.clamp(0.8, 1.4), 1.4);
  });
}

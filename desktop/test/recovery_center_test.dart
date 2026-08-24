// The Recovery Center surface: renders each kind with only its advertised
// actions, performs through the catalog, and states its evidence rule.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/recovery_item.dart';
import 'package:flywheel_desktop/services/recovery_catalog.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/recovery_center.dart';

class _FakeSource implements RecoverySource {
  List<RecoveryItem> items;
  _FakeSource(this.items);

  @override
  String get name => 'fake';

  @override
  Future<List<RecoveryItem>> load() async => items;

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async {
    items = [
      for (final candidate in items)
        if (candidate.ref != item.ref) candidate
    ];
    return true;
  }
}

RecoveryItem _item(RecoveryKind kind, String ref,
        {List<RecoveryActionSpec> actions = const []}) =>
    RecoveryItem(
      kind: kind,
      ref: ref,
      title: 'item $ref',
      detail: 'detail $ref',
      updatedAt: DateTime.parse('2026-08-20T12:00:00Z'),
      actions: actions,
    );

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

void main() {
  testWidgets('the empty state is an honest null, not a fake list',
      (tester) async {
    await tester.pumpWidget(_wrap(
        RecoveryCenter(catalog: RecoveryCatalog([]))));
    await tester.pumpAndSettle();
    expect(find.textContaining('Nothing is waiting'), findsOneWidget);
  });

  testWidgets('items render kind chips and only their advertised actions',
      (tester) async {
    final source = _FakeSource([
      _item(RecoveryKind.unsentChat, 'a', actions: const [
        RecoveryActionSpec('restore', 'Restore'),
      ]),
    ]);
    await tester.pumpWidget(
        _wrap(RecoveryCenter(catalog: RecoveryCatalog([source]))));
    await tester.pumpAndSettle();
    expect(find.textContaining(RegExp('unsent prompt', caseSensitive: false)), findsOneWidget);
    expect(find.text('Restore'), findsOneWidget);
    expect(find.text('Discard'), findsNothing,
        reason: 'an unadvertised action is unreachable, not merely refused');
  });

  testWidgets('performing an action refreshes the surface', (tester) async {
    final source = _FakeSource([
      _item(RecoveryKind.unsentChat, 'a', actions: const [
        RecoveryActionSpec('discard', 'Discard', destructive: true),
      ]),
    ]);
    await tester.pumpWidget(
        _wrap(RecoveryCenter(catalog: RecoveryCatalog([source]))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discard'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Discard: done.'), findsOneWidget);
    expect(find.textContaining('Nothing is waiting'), findsOneWidget,
        reason: 'the successful action removed the only item');
  });

  testWidgets('all six kinds render with their typed labels',
      (tester) async {
    tester.view.physicalSize = const Size(800, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final source = _FakeSource([
      _item(RecoveryKind.unsentChat, 'a'),
      _item(RecoveryKind.dirtyCode, 'b'),
      _item(RecoveryKind.pendingJourney, 'c'),
      _item(RecoveryKind.interruptedOperation, 'd'),
      _item(RecoveryKind.incompleteMigration, 'e'),
      _item(RecoveryKind.failedUpdate, 'f'),
    ]);
    await tester.pumpWidget(
        _wrap(RecoveryCenter(catalog: RecoveryCatalog([source]))));
    await tester.pumpAndSettle();
    for (final label in [
      'unsent prompt',
      'dirty buffer',
      'journey draft',
      'interrupted operation',
      'incomplete migration',
      'failed update',
    ]) {
      expect(find.textContaining(RegExp(label, caseSensitive: false)),
          findsOneWidget,
          reason: label);
    }
  });
}

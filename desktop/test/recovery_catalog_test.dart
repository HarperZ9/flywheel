// The recovery catalog: only advertised actions run, items persist until
// an explicit successful action, failures change nothing, and sources
// that cannot be read contribute honest empties.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/recovery_item.dart';
import 'package:flywheel_desktop/services/recovery_catalog.dart';
import 'package:flywheel_desktop/services/recovery_sources.dart';

class _FakeSource implements RecoverySource {
  List<RecoveryItem> items;
  final Set<String> performed = {};
  bool failLoads = false;
  _FakeSource(this.items);

  @override
  String get name => 'fake';

  @override
  Future<List<RecoveryItem>> load() async {
    if (failLoads) throw StateError('unreadable');
    return items;
  }

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async {
    performed.add('${item.ref}:$actionId');
    if (actionId == 'fail') return false;
    items = [
      for (final candidate in items)
        if (candidate.ref != item.ref) candidate
    ];
    return true;
  }
}

RecoveryItem _chat(String ref) => RecoveryItem(
      kind: RecoveryKind.unsentChat,
      ref: ref,
      title: 'draft $ref',
      detail: 'd',
      updatedAt: DateTime.parse('2026-08-20T12:00:00Z'),
      actions: const [
        RecoveryActionSpec('restore', 'Restore'),
        RecoveryActionSpec('discard', 'Discard', destructive: true),
      ],
    );

void main() {
  test('refresh aggregates all sources', () async {
    final a = _FakeSource([_chat('a')]);
    final b = _FakeSource([
      _chat('b'),
    ]);
    final catalog = RecoveryCatalog([a, b]);
    final items = await catalog.refresh();
    expect(items.map((i) => i.ref), containsAll(['a', 'b']));
  });

  test('an unreadable source contributes an honest empty', () async {
    final broken = _FakeSource([_chat('x')])..failLoads = true;
    final healthy = _FakeSource([_chat('y')]);
    final catalog = RecoveryCatalog([broken, healthy]);
    final items = await catalog.refresh();
    expect(items.map((i) => i.ref), ['y']);
  });

  test('only an advertised action runs', () async {
    final source = _FakeSource([_chat('a')]);
    final catalog = RecoveryCatalog([source]);
    final item = (await catalog.refresh()).single;
    expect(await catalog.perform(item, 'explode'), isFalse);
    expect(source.performed, isEmpty);
  });

  test('a successful discard removes the item; failure keeps it', () async {
    final source = _FakeSource([_chat('a'), _chat('b')]);
    final catalog = RecoveryCatalog([source]);
    var items = await catalog.refresh();
    final first = items.first;

    // A source that refuses the action changes nothing.
    final refusing = _FakeSource([_chat('a'), _chat('b')]);
    final refusingCatalog = RecoveryCatalog([refusing]);
    expect(
        await refusingCatalog.perform(items.first, 'fail'), isFalse);
    expect((await refusingCatalog.refresh()), hasLength(2),
        reason: 'a failed action changes nothing');

    expect(await catalog.perform(first, 'discard'), isTrue);
    items = await catalog.refresh();
    expect(items.map((i) => i.ref), ['b'],
        reason: 'an explicit successful discard removes exactly that item');
  });

  test('the failed-update source is an honest empty until phase 6', () async {
    final source = FailedUpdateRecoverySource();
    expect(await source.load(), isEmpty);
    expect(
        await source.perform(
          RecoveryItem(
              kind: RecoveryKind.failedUpdate,
              ref: 'x',
              title: 't',
              detail: 'd',
              updatedAt: DateTime.now(),
              actions: const []),
          'rollback',
        ),
        isFalse);
  });

  test('the migration source contributes an honest empty', () async {
    expect(await IncompleteMigrationRecoverySource().load(), isEmpty);
  });
}

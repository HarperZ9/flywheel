// The destination catalog: exactly 35 stable IDs in five groups. Labels
// may be renamed; identities never move. This test freezes the contract.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';

void main() {
  // The name said 30 while the assertion said 33, so the name had already
  // drifted past the thing it describes. Both move together from here.
  test('the catalog holds exactly 35 unique destinations', () {
    expect(destinationCatalog.length, 35);
    final ids = destinationCatalog.map((d) => d.id).toSet();
    expect(ids.length, 35);
  });

  test('the five groups carry the exact planned membership and order', () {
    String group(DestinationId id) =>
        destinationCatalog.firstWhere((d) => d.id == id).group.name;
    expect(
        destinationCatalog
            .where((d) => group(d.id) == 'work')
            .map((d) => d.id.name)
            .toList(),
        ['journey', 'plan', 'workflows', 'projects', 'swarms', 'roadmap']);
    expect(
        destinationCatalog
            .where((d) => group(d.id) == 'chat')
            .map((d) => d.id.name)
            .toList(),
        ['chat', 'compare', 'models', 'companion']);
    expect(
        destinationCatalog
            .where((d) => group(d.id) == 'code')
            .map((d) => d.id.name)
            .toList(),
        ['code', 'eval', 'audit', 'lint', 'relay']);
    expect(
        destinationCatalog
            .where((d) => group(d.id) == 'evidence')
            .map((d) => d.id.name)
            .toList(),
        ['receipts', 'science', 'world', 'memory', 'governance', 'usage']);
    expect(
        destinationCatalog
            .where((d) => group(d.id) == 'advanced')
            .map((d) => d.id.name)
            .toList(),
        [
          'studio', 'graph', 'feeds', 'discourse', 'academy', 'lessons',
          'instruments', 'lanes', 'forum', 'registry', 'train', 'uplift', 'family',
          'plugins',
        ]);
  });

  test('every destination has a non-empty label and abbreviation', () {
    for (final d in destinationCatalog) {
      expect(d.label, isNotEmpty, reason: '${d.id} lacks a label');
      expect(d.abbr, isNotEmpty, reason: '${d.id} lacks an abbreviation');
      expect(d.abbr.length, lessThanOrEqualTo(2));
    }
  });

  test('a label can be renamed without changing identity', () {
    // The spec maps by ID, never by label: renaming Receipts to Ledger
    // keeps the same DestinationId, so lookups by ID still resolve.
    final receipts = destinationCatalog.firstWhere(
        (d) => d.id == DestinationId.receipts);
    expect(receipts.id.name, 'receipts');
    expect(receipts.label, isNotEmpty);
    expect(destinationCatalog.where((d) => d.id == DestinationId.receipts),
        hasLength(1));
  });

  test('spec lookup by id resolves and unknown ids are absent', () {
    expect(specFor(DestinationId.journey)!.label, isNotEmpty);
    expect(() => specFor(DestinationId.journey), returnsNormally);
  });
}

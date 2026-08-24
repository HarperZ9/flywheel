// recovery_catalog.dart -- aggregates the recovery sources behind one
// typed read and one mutation path. Items persist until an explicit
// successful action; a failed action changes nothing.
import '../models/recovery_item.dart';

class RecoveryCatalog {
  final List<RecoverySource> sources;
  RecoveryCatalog(this.sources);

  bool _sameItem(RecoveryItem a, RecoveryItem b) =>
      a.kind == b.kind && a.ref == b.ref && a.updatedAt == b.updatedAt;

  Future<List<RecoveryItem>> refresh() async {
    final items = <RecoveryItem>[];
    for (final source in sources) {
      try {
        items.addAll(await source.load());
      } catch (_) {
        // A source that cannot be read contributes an honest empty list;
        // the other kinds still surface.
      }
    }
    return items;
  }

  /// Run one action through the source that owns the item. Only actions
  /// the item advertises are valid; anything else is refused without
  /// touching state.
  Future<bool> perform(RecoveryItem item, String actionId) async {
    if (item.action(actionId) == null) return false;
    for (final source in sources) {
      List<RecoveryItem> owned;
      try {
        owned = await source.load();
      } catch (_) {
        continue;
      }
      if (!owned.any((candidate) => _sameItem(candidate, item))) continue;
      try {
        return await source.perform(item, actionId);
      } catch (_) {
        return false;
      }
    }
    return false;
  }
}

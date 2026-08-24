// recovery_item.dart -- typed recovery facts for the Recovery Center.
//
// Six kinds, fixed action vocabularies, and one rule: nothing is deleted
// automatically, and no server evidence or journey head changes without
// a newly admitted event. An item stays until an explicit successful
// action removes it.
import 'package:flutter/foundation.dart';

enum RecoveryKind {
  unsentChat,
  dirtyCode,
  pendingJourney,
  interruptedOperation,
  incompleteMigration,
  failedUpdate,
}

@immutable
class RecoveryActionSpec {
  final String id;
  final String label;
  final bool destructive;
  const RecoveryActionSpec(this.id, this.label, {this.destructive = false});
}

@immutable
class RecoveryItem {
  final RecoveryKind kind;

  /// A stable ref the owning source understands (a draft ref, a file
  /// path fragment, an operation ref). Never a secret.
  final String ref;
  final String title;
  final String detail;
  final DateTime updatedAt;
  final List<RecoveryActionSpec> actions;

  const RecoveryItem({
    required this.kind,
    required this.ref,
    required this.title,
    required this.detail,
    required this.updatedAt,
    required this.actions,
  });

  RecoveryActionSpec? action(String id) {
    for (final a in actions) {
      if (a.id == id) return a;
    }
    return null;
  }
}

/// One recovery source owns its kind's items and actions. perform() is
/// the only mutation path and returns whether the action succeeded; the
/// catalog re-reads afterwards rather than assuming.
abstract class RecoverySource {
  String get name;
  Future<List<RecoveryItem>> load();
  Future<bool> perform(RecoveryItem item, String actionId);
}

/// The failed-update source stays an honest empty until Phase 6 writes
/// compatible update records; an empty typed result is not a fake list.
class FailedUpdateRecoverySource implements RecoverySource {
  @override
  String get name => 'failed updates';

  @override
  Future<List<RecoveryItem>> load() async => const [];

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async => false;
}

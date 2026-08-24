// recovery_sources.dart -- the concrete RecoverySource implementations
// over the device-local journals: unsent chat drafts, dirty code
// snapshots, and pending journey drafts. Migration and failed-update
// sources contribute honest empties until their records exist.
import '../ide/code_buffer_session.dart';
import '../models/recovery_item.dart';
import '../services/chat_draft_store.dart';
import '../services/journey_draft_store.dart';

class ChatRecoverySource implements RecoverySource {
  final ChatDraftStore store;
  ChatRecoverySource(this.store);

  @override
  String get name => 'unsent chat prompts';

  @override
  Future<List<RecoveryItem>> load() async {
    try {
      return [
        for (final draft in store.load())
          RecoveryItem(
            kind: RecoveryKind.unsentChat,
            ref: draft.draftRef,
            title: draft.text.isEmpty ? 'Empty prompt draft' : draft.text,
            detail: 'unsent chat prompt, device-local',
            updatedAt: draft.updatedAt,
            actions: const [
              RecoveryActionSpec('restore', 'Restore to composer'),
              RecoveryActionSpec('discard', 'Discard', destructive: true),
            ],
          ),
      ];
    } catch (_) {
      return const [];
    }
  }

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async {
    if (actionId == 'restore') return true; // the center hands text back
    if (actionId != 'discard') return false;
    try {
      store.delete(item.ref, expectedTextSha256: _currentSha(item));
      return true;
    } catch (_) {
      return false;
    }
  }

  String _currentSha(RecoveryItem item) {
    for (final draft in store.load()) {
      if (draft.draftRef == item.ref) return draft.textSha256;
    }
    return '';
  }
}

class CodeRecoverySource implements RecoverySource {
  final CodeBufferSession session;
  CodeRecoverySource(this.session);

  @override
  String get name => 'dirty code buffers';

  @override
  Future<List<RecoveryItem>> load() async {
    try {
      return [
        for (final draft in session.drafts)
          RecoveryItem(
            kind: RecoveryKind.dirtyCode,
            ref: draft.path,
            title: draft.path,
            detail: 'unsaved buffer, digest-checked against disk',
            updatedAt: draft.updatedAt,
            actions: const [
              RecoveryActionSpec('inspect', 'Inspect diff'),
              RecoveryActionSpec('restore', 'Restore buffer'),
              RecoveryActionSpec('discard', 'Discard', destructive: true),
            ],
          ),
      ];
    } catch (_) {
      return const [];
    }
  }

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async {
    if (actionId == 'inspect' || actionId == 'restore') return true;
    if (actionId != 'discard') return false;
    return session.discard(item.ref);
  }
}

class JourneyRecoverySource implements RecoverySource {
  final JourneyDraftStore store;

  /// The acknowledgement the store requires before it will delete a
  /// draft: the deletion is itself a custody event, never a silent drop.
  final JourneyDraftAcknowledgement acknowledgement;
  JourneyRecoverySource(this.store, {required this.acknowledgement});

  @override
  String get name => 'pending journey drafts';

  @override
  Future<List<RecoveryItem>> load() async {
    try {
      return [
        for (final draft in store.list())
          RecoveryItem(
            kind: RecoveryKind.pendingJourney,
            ref: draft.draftRef,
            title: 'Journey draft (${draft.kind})',
            detail:
                'device-local draft; opening never mutates server evidence',
            updatedAt: draft.updatedAt,
            actions: const [
              RecoveryActionSpec('open', 'Open in Journey'),
              RecoveryActionSpec('discard', 'Discard', destructive: true),
            ],
          ),
      ];
    } catch (_) {
      return const [];
    }
  }

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async {
    if (actionId == 'open') return true;
    if (actionId != 'discard') return false;
    try {
      store.delete(item.ref, acknowledgement: acknowledgement);
      return true;
    } catch (_) {
      return false;
    }
  }
}

class InterruptedOperationRecoverySource implements RecoverySource {
  final List<RecoveryItem> Function() snapshot;
  InterruptedOperationRecoverySource(this.snapshot);

  @override
  String get name => 'interrupted operations';

  @override
  Future<List<RecoveryItem>> load() async {
    try {
      return snapshot();
    } catch (_) {
      return const [];
    }
  }

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async {
    // Cancellation goes through the operation controller's typed cancel,
    // not here; the center only surfaces the snapshot.
    return false;
  }
}

class IncompleteMigrationRecoverySource implements RecoverySource {
  @override
  String get name => 'incomplete migrations';

  @override
  Future<List<RecoveryItem>> load() async => const [];

  @override
  Future<bool> perform(RecoveryItem item, String actionId) async => false;
}

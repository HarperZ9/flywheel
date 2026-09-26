// Library-private reference derivation and sequence helpers for
// ChatAdmissionController. Split from chat_admission_controller.dart to hold
// that file under the size guideline; a `part` keeps the parent library's
// imports and private scope. No public API changes.

part of 'chat_admission_controller.dart';

String _draftReference(String conversationRef) =>
    'chd_${sha256.convert(utf8.encode('chat:$conversationRef')).toString().substring(0, 32)}';

String _admissionKey(ChatDraft draft) =>
    draft.attemptRef ?? 'legacy:${draft.draftRef}:${draft.textSha256}';

String _attemptReference(String attemptRef) =>
    'chd_${sha256.convert(utf8.encode('admitted:$attemptRef')).toString().substring(0, 32)}';

bool _isAdmittedState(ChatDraftState state) =>
    state == ChatDraftState.admittedPendingHistory ||
    state == ChatDraftState.admittedPendingCleanup;

/// The next conversation number, past every id in memory and in the archive,
/// so a new conversation never takes an archived conversation's id.
int _nextSequence(List<Conversation> conversations,
    [Iterable<String> archived = const []]) {
  var next = 0;
  for (final id in [...conversations.map((c) => c.id), ...archived]) {
    if (!id.startsWith('c')) continue;
    final parsed = int.tryParse(id.substring(1));
    if (parsed != null && parsed >= next) next = parsed + 1;
  }
  return next;
}

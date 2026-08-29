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

int _nextSequence(List<Conversation> conversations) {
  var next = 0;
  for (final conversation in conversations) {
    if (!conversation.id.startsWith('c')) continue;
    final parsed = int.tryParse(conversation.id.substring(1));
    if (parsed != null && parsed >= next) next = parsed + 1;
  }
  return next;
}

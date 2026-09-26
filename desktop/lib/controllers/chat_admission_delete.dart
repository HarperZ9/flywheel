// Deleting a conversation by id everywhere it can live (design 7.9, SP-16).
//
// Drafts go first, then archive segments, then the active file, so a delete
// cut short leaves the conversation visible in the list rather than a draft
// that would recreate it under the deleted id on the next start.

part of 'chat_admission_controller.dart';

extension ChatAdmissionDeletion on ChatAdmissionController {
  /// Removes `conversation` from memory, the drafts, every archive segment
  /// and the active history file. False when any of them could not be
  /// rewritten; the history banner then says the delete is incomplete.
  bool deleteConversation(Conversation conversation) {
    final id = conversation.id;
    if (!_deleteDraftsOf(id)) {
      historyStore.status
        ..deleteIncomplete = true
        ..changed();
      return false;
    }
    conversations.removeWhere((c) => c.id == id);
    return historyStore.deleteConversation(id, conversations);
  }

  bool _deleteDraftsOf(String id) {
    _drafts.remove(id);
    _admitted.removeWhere((_, draft) => draft.conversationRef == id);
    try {
      for (final draft in draftStore.load()) {
        if (draft.conversationRef != id) continue;
        draftStore.delete(draft.draftRef,
            expectedTextSha256: draft.textSha256);
      }
      return true;
    } on ChatDraftStoreException {
      return false;
    }
  }
}

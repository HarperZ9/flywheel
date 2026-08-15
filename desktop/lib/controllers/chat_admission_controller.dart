import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../models/chat.dart';
import '../services/chat_draft_store.dart';
import '../services/chat_store.dart';

typedef ChatAdmissionDecision = ({
  PromptDisposition disposition,
  bool visible,
});

final class ChatAdmissionController {
  ChatAdmissionController(this.historyStore, this.draftStore);

  final ChatStore historyStore;
  final ChatDraftStore draftStore;
  final conversations = <Conversation>[];
  final _drafts = <String, ChatDraft>{};
  final _admitted = <String>{};
  var _sequence = 0;

  void restore() {
    conversations.addAll(historyStore.load());
    try {
      for (final draft in draftStore.load()) {
        _drafts[draft.conversationRef] = draft;
        final matches = conversations
            .where((item) => item.id == draft.conversationRef)
            .firstOrNull;
        if (matches == null) {
          conversations.add(Conversation(id: draft.conversationRef));
        }
        if (draft.state == ChatDraftState.submitting &&
            matches?.messages.any((message) =>
                    message.isUser && message.text == draft.text) ==
                true) {
          _admitted.add(_admissionKey(draft));
        }
      }
    } on ChatDraftStoreException {/* corrupt local bytes are not promoted */}
    _sequence = _nextSequence(conversations);
  }

  Conversation blankConversation(String? model) =>
      Conversation(id: 'c${_sequence++}', model: model);

  String draftText(Conversation conversation) =>
      _drafts[conversation.id]?.text ?? '';

  bool persistHistory() => historyStore.save(conversations);

  void changeDraft(Conversation conversation, String text) {
    final existing = _drafts[conversation.id];
    if (text.trim().isEmpty) {
      _deleteExisting(existing);
      return;
    }
    ChatDraft draft;
    try {
      draft = _draft(conversation, text, ChatDraftState.dirty);
    } on ChatDraftStoreException {
      _deleteExisting(existing);
      return;
    }
    try {
      draftStore.save(draft);
      _drafts[conversation.id] = draft;
    } on ChatDraftStoreException {/* current editor text stays authoritative */}
  }

  ChatDraft? prepare(Conversation conversation, String text) {
    try {
      final draft = _draft(conversation, text, ChatDraftState.submitting);
      if (_admitted.contains(_admissionKey(draft))) return null;
      draftStore.save(draft);
      _drafts[conversation.id] = draft;
      return draft;
    } on ChatDraftStoreException {
      return null;
    }
  }

  ChatAdmissionDecision acceptFirst(
      Conversation conversation, ChatDraft submitted, ChatMessage assistant) {
    conversation.messages.addAll([
      ChatMessage(role: 'user', text: submitted.text),
      assistant,
    ]);
    conversation.titleFromFirstMessage();
    if (!historyStore.save(conversations)) {
      conversation.messages.removeRange(
          conversation.messages.length - 2, conversation.messages.length);
      retain(submitted);
      _admitted.add(_admissionKey(submitted));
      return (disposition: PromptDisposition.retained, visible: false);
    }
    if (!_cleanSubmitted(submitted)) {
      _admitted.add(_admissionKey(submitted));
      return (disposition: PromptDisposition.retained, visible: true);
    }
    return (disposition: PromptDisposition.accepted, visible: true);
  }

  void retain(ChatDraft submitted) {
    final current = _drafts[submitted.conversationRef];
    if (current?.textSha256 != submitted.textSha256) return;
    try {
      final retained = _draft(Conversation(id: submitted.conversationRef),
          submitted.text, ChatDraftState.retained);
      draftStore.save(retained);
      _drafts[retained.conversationRef] = retained;
    } on ChatDraftStoreException {/* submitting bytes remain recoverable */}
  }

  ChatDraft _draft(
          Conversation conversation, String text, ChatDraftState state) =>
      ChatDraft(
          draftRef: _draftReference(conversation.id),
          conversationRef: conversation.id,
          text: text,
          state: state,
          updatedAt: DateTime.now().toUtc());

  bool _cleanSubmitted(ChatDraft submitted) {
    try {
      draftStore.delete(submitted.draftRef,
          expectedTextSha256: submitted.textSha256);
      _drafts.remove(submitted.conversationRef);
      return true;
    } on ChatDraftStoreException catch (error) {
      return error.failure == ChatDraftFailure.digestMismatch ||
          error.failure == ChatDraftFailure.notFound;
    }
  }

  void _deleteExisting(ChatDraft? draft) {
    if (draft == null) return;
    try {
      draftStore.delete(draft.draftRef, expectedTextSha256: draft.textSha256);
      _drafts.remove(draft.conversationRef);
    } on ChatDraftStoreException {/* prior recoverable bytes remain */}
  }
}

String _draftReference(String conversationRef) =>
    'chd_${sha256.convert(utf8.encode('chat:$conversationRef')).toString().substring(0, 32)}';

String _admissionKey(ChatDraft draft) =>
    '${draft.conversationRef}:${draft.textSha256}';

int _nextSequence(List<Conversation> conversations) {
  var next = 0;
  for (final conversation in conversations) {
    if (!conversation.id.startsWith('c')) continue;
    final parsed = int.tryParse(conversation.id.substring(1));
    if (parsed != null && parsed >= next) next = parsed + 1;
  }
  return next;
}

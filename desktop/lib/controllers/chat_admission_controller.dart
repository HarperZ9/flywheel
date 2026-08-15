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
  final _admitted = <String, ChatDraft>{};
  var _sequence = 0;

  void restore() {
    conversations.addAll(historyStore.load());
    try {
      for (final draft in draftStore.load()) {
        final conversation = _conversation(draft.conversationRef);
        if (_isAdmittedState(draft.state)) {
          _admitted[_admissionKey(draft)] = draft;
        } else if (draft.state == ChatDraftState.submitting) {
          _restoreSubmitting(conversation, draft);
        } else {
          _drafts[draft.conversationRef] = draft;
        }
      }
    } on ChatDraftStoreException {/* corrupt local bytes are not promoted */}
    _sequence = _nextSequence(conversations);
  }

  Conversation blankConversation(String? model) =>
      Conversation(id: 'c${_sequence++}', model: model);

  String draftText(Conversation conversation) =>
      _drafts[conversation.id]?.text ??
      _admittedForConversation(conversation.id)?.text ??
      '';

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
    if (_admitted.containsKey(_admissionKey(draft))) return;
    try {
      draftStore.save(draft);
      _drafts[conversation.id] = draft;
    } on ChatDraftStoreException {/* current editor text stays authoritative */}
  }

  ChatDraft? prepare(Conversation conversation, String text) {
    try {
      final draft = _draft(conversation, text, ChatDraftState.submitting);
      if (_admitted.containsKey(_admissionKey(draft))) return null;
      draftStore.save(draft);
      _drafts[conversation.id] = draft;
      return draft;
    } on ChatDraftStoreException {
      return null;
    }
  }

  ChatAdmissionDecision acceptFirst(
      Conversation conversation, ChatDraft submitted, ChatMessage assistant) {
    if (!_markAdmitted(
        submitted, ChatDraftState.admittedPendingHistory, assistant.toJson())) {
      return (disposition: PromptDisposition.retained, visible: false);
    }
    var pending = _admitted[_admissionKey(submitted)]!;
    final priorTitle = conversation.title;
    conversation.messages.addAll([
      ChatMessage(role: 'user', text: submitted.text),
      assistant,
    ]);
    conversation.titleFromFirstMessage();
    if (!historyStore.save(conversations)) {
      conversation.messages.removeRange(
          conversation.messages.length - 2, conversation.messages.length);
      conversation.title = priorTitle;
      return (disposition: PromptDisposition.retained, visible: false);
    }
    if (!_markAdmitted(pending, ChatDraftState.admittedPendingCleanup,
        pending.assistantEvent!)) {
      assistant.streaming = false;
      return (disposition: PromptDisposition.retained, visible: false);
    }
    pending = _admitted[_admissionKey(pending)]!;
    if (!_cleanAdmitted(pending)) {
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

  PromptDisposition? reconcileAdmitted(Conversation conversation, String text) {
    ChatDraft candidate;
    try {
      candidate = _draft(conversation, text, ChatDraftState.dirty);
    } on ChatDraftStoreException {
      return null;
    }
    final pending = _admitted[_admissionKey(candidate)];
    if (pending == null) return null;
    return _reconcile(conversation, pending);
  }

  PromptDisposition _reconcile(Conversation conversation, ChatDraft pending) {
    final event = pending.assistantEvent;
    if (event == null) return PromptDisposition.retained;
    final pairExists = chatHasAdmittedPair(conversation, pending.text, event);
    final priorTitle = conversation.title;
    if (!pairExists) {
      conversation.messages.addAll([
        ChatMessage(role: 'user', text: pending.text),
        ChatMessage.fromJson(event),
      ]);
      conversation.titleFromFirstMessage();
    }
    if (!historyStore.save(conversations)) {
      if (!pairExists) {
        conversation.messages.removeRange(
            conversation.messages.length - 2, conversation.messages.length);
        conversation.title = priorTitle;
      }
      return PromptDisposition.retained;
    }
    if (pending.state != ChatDraftState.admittedPendingCleanup) {
      if (!_markAdmitted(
          pending, ChatDraftState.admittedPendingCleanup, event)) {
        return PromptDisposition.retained;
      }
      pending = _admitted[_admissionKey(pending)]!;
    }
    return _cleanAdmitted(pending)
        ? PromptDisposition.accepted
        : PromptDisposition.retained;
  }

  bool _markAdmitted(ChatDraft submitted, ChatDraftState state,
      Map<String, dynamic> assistantEvent) {
    final pending = ChatDraft(
        draftRef: _admittedReference(submitted),
        conversationRef: submitted.conversationRef,
        text: submitted.text,
        state: state,
        updatedAt: DateTime.now().toUtc(),
        assistantEvent: assistantEvent);
    final key = _admissionKey(pending);
    final fallback = _admitted[key] ?? submitted;
    try {
      draftStore.save(pending);
      _admitted[key] = pending;
      final current = _drafts[pending.conversationRef];
      if (current?.textSha256 == pending.textSha256) {
        _drafts.remove(pending.conversationRef);
      }
      return true;
    } on ChatDraftStoreException {
      _admitted[key] = fallback;
      return false;
    }
  }

  bool _cleanAdmitted(ChatDraft pending) {
    final current = _drafts[pending.conversationRef];
    try {
      if (current?.textSha256 == pending.textSha256) {
        draftStore.delete(current!.draftRef,
            expectedTextSha256: current.textSha256);
        _drafts.remove(pending.conversationRef);
      }
      draftStore.delete(pending.draftRef,
          expectedTextSha256: pending.textSha256);
      _admitted.remove(_admissionKey(pending));
      return true;
    } on ChatDraftStoreException {
      return false;
    }
  }

  ChatDraft _draft(
          Conversation conversation, String text, ChatDraftState state) =>
      ChatDraft(
          draftRef: _draftReference(conversation.id),
          conversationRef: conversation.id,
          text: text,
          state: state,
          updatedAt: DateTime.now().toUtc());

  void _deleteExisting(ChatDraft? draft) {
    if (draft == null) return;
    try {
      draftStore.delete(draft.draftRef, expectedTextSha256: draft.textSha256);
      _drafts.remove(draft.conversationRef);
    } on ChatDraftStoreException {/* prior recoverable bytes remain */}
  }

  Conversation _conversation(String ref) {
    for (final conversation in conversations) {
      if (conversation.id == ref) return conversation;
    }
    final conversation = Conversation(id: ref);
    conversations.add(conversation);
    return conversation;
  }

  void _restoreSubmitting(Conversation conversation, ChatDraft draft) {
    final assistant = chatHistoryAssistant(conversation, draft.text);
    if (assistant != null &&
        _markAdmitted(
            draft, ChatDraftState.admittedPendingCleanup, assistant.toJson())) {
      return;
    }
    _admitted[_admissionKey(draft)] = draft;
  }

  ChatDraft? _admittedForConversation(String conversationRef) {
    ChatDraft? newest;
    for (final draft in _admitted.values) {
      if (draft.conversationRef != conversationRef) continue;
      if (newest == null || draft.updatedAt.isAfter(newest.updatedAt)) {
        newest = draft;
      }
    }
    return newest;
  }
}

String _draftReference(String conversationRef) =>
    'chd_${sha256.convert(utf8.encode('chat:$conversationRef')).toString().substring(0, 32)}';

String _admissionKey(ChatDraft draft) =>
    '${draft.conversationRef}:${draft.textSha256}';

String _admittedReference(ChatDraft draft) =>
    'chd_${sha256.convert(utf8.encode('admitted:${_admissionKey(draft)}')).toString().substring(0, 32)}';

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

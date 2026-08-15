import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import '../models/chat.dart';
import 'journey_session_store.dart';

const _schema = 'flywheel.desktop-chat-drafts/v1';
final _draftRef = RegExp(r'^chd_[0-9a-f]{32}$');
final _conversationRef = RegExp(r'^c[0-9]+$');
final _sha256 = RegExp(r'^[0-9a-f]{64}$');

enum ChatDraftState {
  dirty,
  submitting,
  retained,
  admittedPendingHistory,
  admittedPendingCleanup,
}

extension on ChatDraftState {
  String get wire => switch (this) {
        ChatDraftState.dirty => 'dirty',
        ChatDraftState.submitting => 'submitting',
        ChatDraftState.retained => 'retained',
        ChatDraftState.admittedPendingHistory => 'admitted_pending_history',
        ChatDraftState.admittedPendingCleanup => 'admitted_pending_cleanup',
      };
}

enum ChatDraftFailure {
  invalidRecord,
  corruptStore,
  writeFailed,
  notFound,
  digestMismatch,
}

final class ChatDraftStoreException implements Exception {
  const ChatDraftStoreException(this.failure);
  final ChatDraftFailure failure;

  @override
  String toString() => 'Chat draft store failure: ${failure.name}';
}

final class ChatDraft {
  factory ChatDraft({
    required String draftRef,
    required String conversationRef,
    required String text,
    required ChatDraftState state,
    required DateTime updatedAt,
    Map<String, dynamic>? assistantEvent,
    String? attemptRef,
  }) {
    try {
      _require(_draftRef.hasMatch(draftRef));
      _require(_conversationRef.hasMatch(conversationRef));
      _require(text.trim().isNotEmpty && updatedAt.isUtc);
      _require(attemptRef == null || isChatAttemptRef(attemptRef));
      _require(_isAdmittedState(state) == (assistantEvent != null));
      final guarded = snapshotJourneyLocalJson({
        'text': text,
        if (attemptRef != null) 'attempt_ref': attemptRef,
        if (assistantEvent != null) 'assistant': assistantEvent
      },
          safeText: safeChatLocalText,
          secretKey: isChatLocalSecretKey,
          safeRef: safeChatLocalRef);
      final exact = guarded['text'] as String;
      final exactAttempt = guarded['attempt_ref'] as String?;
      final assistant = assistantEvent == null
          ? null
          : _validAssistant(guarded['assistant'], exactAttempt);
      return ChatDraft._(draftRef, conversationRef, exact, _textSha(exact),
          state, updatedAt.toUtc(), assistant, exactAttempt);
    } catch (_) {
      throw const ChatDraftStoreException(ChatDraftFailure.invalidRecord);
    }
  }

  const ChatDraft._(
      this.draftRef,
      this.conversationRef,
      this.text,
      this.textSha256,
      this.state,
      this.updatedAt,
      this.assistantEvent,
      this.attemptRef);
  final String draftRef;
  final String conversationRef;
  final String text;
  final String textSha256;
  final ChatDraftState state;
  final DateTime updatedAt;
  final Map<String, dynamic>? assistantEvent;
  final String? attemptRef;
}

typedef ChatBeforeRename = void Function(File temporary);
typedef ChatRenameFile = void Function(File temporary, String targetPath);
typedef ChatTemporaryFile = File Function(File target);

final class ChatDraftStore {
  ChatDraftStore(
      {File? file, this.beforeRename, this.renameFile, this.temporaryFile})
      : storageFile = file ?? File(journeyLocalDefaultPath('chat-drafts.json'));

  final File storageFile;
  final ChatBeforeRename? beforeRename;
  final ChatRenameFile? renameFile;
  final ChatTemporaryFile? temporaryFile;

  List<ChatDraft> load() {
    if (!storageFile.existsSync()) return const [];
    try {
      final root = readJourneyLocalObject(storageFile);
      _exactKeys(root, const {'drafts', 'schema'});
      _require(root['schema'] == _schema && root['drafts'] is List);
      final drafts = <ChatDraft>[];
      final draftRefs = <String>{};
      final activeConversations = <String>{};
      for (final raw in root['drafts'] as List) {
        _require(raw is Map<String, dynamic>);
        final draft = _decode(raw as Map<String, dynamic>);
        _require(draftRefs.add(draft.draftRef));
        _require(_isAdmittedState(draft.state) ||
            activeConversations.add(draft.conversationRef));
        drafts.add(draft);
      }
      return List.unmodifiable(drafts);
    } catch (_) {
      throw const ChatDraftStoreException(ChatDraftFailure.corruptStore);
    }
  }

  void save(ChatDraft draft) {
    final drafts = load().where((item) => !_superseded(item, draft)).toList()
      ..add(draft)
      ..sort((a, b) => a.draftRef.compareTo(b.draftRef));
    _write(drafts);
  }

  void delete(String draftRef, {required String expectedTextSha256}) {
    final drafts = load();
    final index = drafts.indexWhere((draft) => draft.draftRef == draftRef);
    if (index < 0) {
      throw const ChatDraftStoreException(ChatDraftFailure.notFound);
    }
    if (!_sha256.hasMatch(expectedTextSha256) ||
        drafts[index].textSha256 != expectedTextSha256) {
      throw const ChatDraftStoreException(ChatDraftFailure.digestMismatch);
    }
    _write([...drafts]..removeAt(index));
  }

  void _write(List<ChatDraft> drafts) {
    final value = {
      'drafts': drafts.map(_encode).toList(growable: false),
      'schema': _schema,
    };
    Map<String, dynamic> guarded;
    try {
      guarded = snapshotJourneyLocalJson(value,
          safeText: (_) => true, secretKey: (_) => false, safeRef: (_) => true);
    } catch (_) {
      throw const ChatDraftStoreException(ChatDraftFailure.invalidRecord);
    }
    final prior =
        storageFile.existsSync() ? storageFile.readAsBytesSync() : null;
    try {
      writeJourneyLocalObject(storageFile, guarded,
          beforeRename: beforeRename,
          renameFile: renameFile,
          temporaryFile: temporaryFile);
    } catch (_) {
      _restore(prior);
      throw const ChatDraftStoreException(ChatDraftFailure.writeFailed);
    }
  }

  void _restore(List<int>? prior) {
    try {
      if (prior == null) {
        if (storageFile.existsSync()) storageFile.deleteSync();
        return;
      }
      final decoded = jsonDecode(utf8.decode(prior));
      writeJourneyLocalObject(storageFile, decoded);
    } catch (_) {
      throw const ChatDraftStoreException(ChatDraftFailure.writeFailed);
    }
  }
}

ChatDraft _decode(Map<String, dynamic> raw) {
  final state = _parseState(raw['state']);
  final keys = <String>{
    'conversation_ref',
    'draft_ref',
    'state',
    'text',
    'text_sha256',
    'updated_at'
  };
  if (_isAdmittedState(state)) keys.add('assistant');
  if (raw.containsKey('attempt_ref')) keys.add('attempt_ref');
  _exactKeys(raw, keys);
  _require(raw['conversation_ref'] is String && raw['draft_ref'] is String);
  _require(raw['text'] is String && raw['text_sha256'] is String);
  _require(raw['state'] is String && raw['updated_at'] is String);
  final updatedAt = DateTime.tryParse(raw['updated_at'] as String);
  _require(updatedAt != null && updatedAt.isUtc);
  final draft = ChatDraft(
      draftRef: raw['draft_ref'] as String,
      conversationRef: raw['conversation_ref'] as String,
      text: raw['text'] as String,
      state: state,
      updatedAt: updatedAt!,
      assistantEvent: raw['assistant'] as Map<String, dynamic>?,
      attemptRef: raw['attempt_ref'] as String?);
  _require(raw['text_sha256'] == draft.textSha256);
  return draft;
}

Map<String, dynamic> _encode(ChatDraft draft) => {
      if (draft.assistantEvent != null) 'assistant': draft.assistantEvent,
      if (draft.attemptRef != null) 'attempt_ref': draft.attemptRef,
      'conversation_ref': draft.conversationRef,
      'draft_ref': draft.draftRef,
      'state': draft.state.wire,
      'text': draft.text,
      'text_sha256': draft.textSha256,
      'updated_at': draft.updatedAt.toIso8601String(),
    };

Map<String, dynamic> _validAssistant(Object? value, String? attemptRef) {
  _require(value is Map<String, dynamic>);
  final assistant = value as Map<String, dynamic>;
  final expected = <String>{'role', 'text'};
  if (assistant.containsKey('receipt')) expected.add('receipt');
  if (assistant.containsKey('attempt_ref')) expected.add('attempt_ref');
  _exactKeys(assistant, expected);
  _require(assistant['role'] == 'assistant' && assistant['text'] is String);
  _require(!assistant.containsKey('receipt') ||
      assistant['receipt'] is Map<String, dynamic>);
  _require((assistant['text'] as String).isNotEmpty ||
      assistant.containsKey('receipt'));
  _require(assistant['attempt_ref'] == attemptRef);
  return assistant;
}

ChatDraftState _parseState(Object? raw) {
  for (final state in ChatDraftState.values) {
    if (state.wire == raw) return state;
  }
  throw const ChatDraftStoreException(ChatDraftFailure.invalidRecord);
}

bool _isAdmittedState(ChatDraftState state) => state.index >= 3;
bool _superseded(ChatDraft stored, ChatDraft incoming) {
  if (stored.draftRef == incoming.draftRef) return true;
  if (stored.conversationRef != incoming.conversationRef) return false;
  if (!_isAdmittedState(incoming.state)) return !_isAdmittedState(stored.state);
  return incoming.attemptRef != null &&
      !_isAdmittedState(stored.state) &&
      stored.attemptRef == incoming.attemptRef;
}

String _textSha(String text) => sha256.convert(utf8.encode(text)).toString();
void _require(bool condition) => condition
    ? null
    : throw const ChatDraftStoreException(ChatDraftFailure.invalidRecord);
void _exactKeys(Map<String, dynamic> value, Set<String> expected) =>
    _require(value.length == expected.length &&
        value.keys.toSet().containsAll(expected));

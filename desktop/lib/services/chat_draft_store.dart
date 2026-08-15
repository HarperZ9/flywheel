import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import 'journey_session_store.dart';

const _schema = 'flywheel.desktop-chat-drafts/v1';
final _draftRef = RegExp(r'^chd_[0-9a-f]{32}$');
final _conversationRef = RegExp(r'^c[0-9]+$');
final _sha256 = RegExp(r'^[0-9a-f]{64}$');
final _windowsPath = RegExp(r'[A-Za-z]:[\\/]');
final _uncPath = RegExp(r'(?:\\\\|//)[^\\/\s]+[\\/][^\s]+');
final _privatePath = RegExp(r'(?:^|[\s=(\[{,:;])/(?!/)[^\s]+|/'
    r'(?:Users|home|private|tmp|var|etc|root|opt|mnt|srv|usr|bin|sbin|lib|'
    r'Applications|Volumes|dev|proc|sys|run)(?:/|$)');
final _fileUri = RegExp(r'(?<![A-Za-z0-9+.-])file:', caseSensitive: false);
final _secretValue = RegExp(
    r'(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-(?:live|proj|ant)[A-Za-z0-9_-]{10,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b)');
final _assignedSecret = RegExp(
    r'\b(?:secret|password|passwd|api_key|access_key|token|credential)\s*[:=]\s*["\x27]?[A-Za-z0-9/+_-]{12,}',
    caseSensitive: false);
final _secretKey = RegExp(r'^(?:api_keys?|access_tokens?|refresh_tokens?|'
    r'tokens?|passwords?|secrets?|credentials?|private_keys?|authorizations?|'
    r'cookies?|environments?|envs?|passwds?|access_keys?|.+_(?:api_keys?|'
    r'private_keys?|passwords?|secrets?|credentials?|tokens?))$');

enum ChatDraftState { dirty, submitting, retained }

extension on ChatDraftState {
  String get wire => switch (this) {
        ChatDraftState.dirty => 'dirty',
        ChatDraftState.submitting => 'submitting',
        ChatDraftState.retained => 'retained',
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
  }) {
    try {
      _require(_draftRef.hasMatch(draftRef));
      _require(_conversationRef.hasMatch(conversationRef));
      _require(text.trim().isNotEmpty && updatedAt.isUtc);
      final guarded = snapshotJourneyLocalJson({'text': text},
          safeText: _safeText, secretKey: _isSecretKey, safeRef: _safeRef);
      final exact = guarded['text'] as String;
      return ChatDraft._(draftRef, conversationRef, exact, _textSha(exact),
          state, updatedAt.toUtc());
    } catch (_) {
      throw const ChatDraftStoreException(ChatDraftFailure.invalidRecord);
    }
  }

  const ChatDraft._(this.draftRef, this.conversationRef, this.text,
      this.textSha256, this.state, this.updatedAt);
  final String draftRef;
  final String conversationRef;
  final String text;
  final String textSha256;
  final ChatDraftState state;
  final DateTime updatedAt;
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
      final conversationRefs = <String>{};
      for (final raw in root['drafts'] as List) {
        _require(raw is Map<String, dynamic>);
        final draft = _decode(raw as Map<String, dynamic>);
        _require(draftRefs.add(draft.draftRef));
        _require(conversationRefs.add(draft.conversationRef));
        drafts.add(draft);
      }
      return List.unmodifiable(drafts);
    } catch (_) {
      throw const ChatDraftStoreException(ChatDraftFailure.corruptStore);
    }
  }

  void save(ChatDraft draft) {
    final drafts = load()
        .where((item) =>
            item.draftRef != draft.draftRef &&
            item.conversationRef != draft.conversationRef)
        .toList()
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
  _exactKeys(raw, const {
    'conversation_ref',
    'draft_ref',
    'state',
    'text',
    'text_sha256',
    'updated_at'
  });
  _require(raw['conversation_ref'] is String && raw['draft_ref'] is String);
  _require(raw['text'] is String && raw['text_sha256'] is String);
  _require(raw['state'] is String && raw['updated_at'] is String);
  final updatedAt = DateTime.tryParse(raw['updated_at'] as String);
  _require(updatedAt != null && updatedAt.isUtc);
  final draft = ChatDraft(
      draftRef: raw['draft_ref'] as String,
      conversationRef: raw['conversation_ref'] as String,
      text: raw['text'] as String,
      state: _parseState(raw['state']),
      updatedAt: updatedAt!);
  _require(raw['text_sha256'] == draft.textSha256);
  return draft;
}

Map<String, dynamic> _encode(ChatDraft draft) => {
      'conversation_ref': draft.conversationRef,
      'draft_ref': draft.draftRef,
      'state': draft.state.wire,
      'text': draft.text,
      'text_sha256': draft.textSha256,
      'updated_at': draft.updatedAt.toIso8601String(),
    };

ChatDraftState _parseState(Object? raw) {
  for (final state in ChatDraftState.values) {
    if (state.wire == raw) return state;
  }
  throw const ChatDraftStoreException(ChatDraftFailure.invalidRecord);
}

String _textSha(String text) => sha256.convert(utf8.encode(text)).toString();
void _require(bool condition) => condition
    ? null
    : throw const ChatDraftStoreException(ChatDraftFailure.invalidRecord);
void _exactKeys(Map<String, dynamic> value, Set<String> expected) =>
    _require(value.length == expected.length &&
        value.keys.toSet().containsAll(expected));

bool _safeText(String value) {
  final decoded = _decodedText(value);
  return _safeForm(value) && _safeForm(decoded);
}

bool _safeForm(String value) =>
    !_windowsPath.hasMatch(value) &&
    !_uncPath.hasMatch(value) &&
    !_privatePath.hasMatch(value) &&
    !_fileUri.hasMatch(value) &&
    !_secretValue.hasMatch(value) &&
    !_assignedSecret.hasMatch(value);

bool _isSecretKey(String key) =>
    _secretKey.hasMatch(_decodedText(key).toLowerCase().replaceAll('-', '_'));
bool _safeRef(String value) =>
    value.isNotEmpty && value.length <= 256 && !value.contains(':');

String _decodedText(String value) {
  final result = StringBuffer();
  for (var index = 0; index < value.length;) {
    if (value.codeUnitAt(index) != 0x25) {
      result.writeCharCode(value.codeUnitAt(index++));
      continue;
    }
    final next = index + 1 < value.length ? value.codeUnitAt(index + 1) : null;
    if (index + 2 >= value.length ||
        !_hex(next) ||
        !_hex(value.codeUnitAt(index + 2))) {
      result.write('%');
      index++;
      continue;
    }
    final start = index;
    while (index + 2 < value.length &&
        value.codeUnitAt(index) == 0x25 &&
        _hex(value.codeUnitAt(index + 1)) &&
        _hex(value.codeUnitAt(index + 2))) {
      index += 3;
    }
    try {
      result.write(Uri.decodeComponent(value.substring(start, index)));
    } catch (_) {
      _require(false);
    }
  }
  return result.toString();
}

bool _hex(int? value) =>
    value != null &&
    ((value >= 0x30 && value <= 0x39) ||
        (value >= 0x41 && value <= 0x46) ||
        (value >= 0x61 && value <= 0x66));

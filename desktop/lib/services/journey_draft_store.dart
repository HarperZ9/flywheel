import 'dart:io';

import 'journey_session_store.dart';

export 'journey_session_store.dart'
    show JourneyLocalFailure, JourneyLocalStoreException;

const _draftSchema = 'flywheel.desktop-journey-drafts/v1';
final _draftRef = RegExp(r'^dft_[0-9a-f]{32}$');
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _sha256 = RegExp(r'^[0-9a-f]{64}$');
final _kind = RegExp(r'^[a-z][a-z0-9_]{0,31}$');
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
final _secretKeyName = RegExp(r'^(?:api_keys?|access_tokens?|refresh_tokens?|'
    r'tokens?|passwords?|secrets?|credentials?|private_keys?|authorizations?|'
    r'cookies?|environments?|envs?|passwds?|access_keys?|.+_(?:api_keys?|'
    r'private_keys?|passwords?|secrets?|credentials?|tokens?))$');

enum JourneyDraftState {
  clean,
  dirty,
  saving,
  saved,
  saveFailed,
  recoveryAvailable,
}

extension on JourneyDraftState {
  String get wire => switch (this) {
        JourneyDraftState.clean => 'clean',
        JourneyDraftState.dirty => 'dirty',
        JourneyDraftState.saving => 'saving',
        JourneyDraftState.saved => 'saved',
        JourneyDraftState.saveFailed => 'save_failed',
        JourneyDraftState.recoveryAvailable => 'recovery_available',
      };
}

class JourneyDraftAcknowledgement {
  const JourneyDraftAcknowledgement(this.clientRequestId, this.eventHeadSha256);
  final String clientRequestId;
  final String eventHeadSha256;
}

class JourneyDraft {
  factory JourneyDraft({
    required String draftRef,
    String? journeyRef,
    String? baseEventHeadSha256,
    required String kind,
    required Map<Object?, Object?> payload,
    required JourneyDraftState state,
    required DateTime updatedAt,
  }) {
    _require(_draftRef.hasMatch(draftRef));
    _require(journeyRef == null || _journeyRef.hasMatch(journeyRef));
    _require(
        baseEventHeadSha256 == null || _sha256.hasMatch(baseEventHeadSha256));
    _require(_kind.hasMatch(kind));
    final copy = snapshotJourneyLocalJson(payload,
        safeText: _safeText, secretKey: _secretKey, safeRef: _safeRef);
    final request = copy['client_request_id'];
    _require(request is String && request.isNotEmpty && _safeText(request));
    return JourneyDraft._(draftRef, journeyRef, baseEventHeadSha256, kind, copy,
        journeyLocalSha256(copy), state, updatedAt.toUtc());
  }

  const JourneyDraft._(this.draftRef, this.journeyRef, this.baseEventHeadSha256,
      this.kind, this.payload, this.payloadSha256, this.state, this.updatedAt);
  final String draftRef;
  final String? journeyRef;
  final String? baseEventHeadSha256;
  final String kind;
  final Map<String, dynamic> payload;
  final String payloadSha256;
  final JourneyDraftState state;
  final DateTime updatedAt;
}

class JourneyDraftStore {
  JourneyDraftStore(
      {File? file, this.beforeRename, this.renameFile, this.temporaryFile})
      : storageFile =
            file ?? File(journeyLocalDefaultPath('journey-drafts.json'));

  final File storageFile;
  final JourneyBeforeRename? beforeRename;
  final JourneyRenameFile? renameFile;
  final JourneyTemporaryFile? temporaryFile;

  List<JourneyDraft> list() {
    if (!storageFile.existsSync()) return const [];
    try {
      final root = readJourneyLocalObject(storageFile);
      _exactKeys(root, const {'schema', 'drafts'});
      _require(root['schema'] == _draftSchema);
      final raw = root['drafts'];
      _require(raw is List);
      final refs = <String>{};
      final drafts = <JourneyDraft>[];
      for (final item in raw as List) {
        _require(item is Map<String, dynamic>);
        final draft = _decodeDraft(item as Map<String, dynamic>);
        _require(refs.add(draft.draftRef));
        drafts.add(draft);
      }
      return List.unmodifiable(drafts);
    } catch (_) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.corruptStore);
    }
  }

  void save(JourneyDraft draft) {
    final drafts =
        list().where((item) => item.draftRef != draft.draftRef).toList()
          ..add(draft)
          ..sort((a, b) => a.draftRef.compareTo(b.draftRef));
    _write(drafts);
  }

  void markFailed(String draftRef, {DateTime? updatedAt}) {
    final drafts = list();
    final index = drafts.indexWhere((item) => item.draftRef == draftRef);
    if (index < 0) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.notFound);
    }
    final old = drafts[index];
    final replacement = JourneyDraft(
        draftRef: old.draftRef,
        journeyRef: old.journeyRef,
        baseEventHeadSha256: old.baseEventHeadSha256,
        kind: old.kind,
        payload: old.payload,
        state: JourneyDraftState.saveFailed,
        updatedAt: updatedAt ?? DateTime.now().toUtc());
    save(replacement);
  }

  void delete(String draftRef,
      {required JourneyDraftAcknowledgement acknowledgement}) {
    final drafts = list();
    final index = drafts.indexWhere((item) => item.draftRef == draftRef);
    if (index < 0) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.notFound);
    }
    final storedRequest = drafts[index].payload['client_request_id'];
    final storedHead = drafts[index].baseEventHeadSha256;
    if (storedRequest != acknowledgement.clientRequestId ||
        !_sha256.hasMatch(acknowledgement.eventHeadSha256) ||
        (storedHead != null && storedHead == acknowledgement.eventHeadSha256)) {
      throw const JourneyLocalStoreException(
          JourneyLocalFailure.acknowledgementMismatch);
    }
    _write([...drafts]..removeAt(index));
  }

  void _write(List<JourneyDraft> drafts) {
    final value = {
      'drafts': drafts.map(_encodeDraft).toList(growable: false),
      'schema': _draftSchema,
    };
    writeJourneyLocalObject(storageFile, value,
        beforeRename: beforeRename,
        renameFile: renameFile,
        temporaryFile: temporaryFile);
  }
}

JourneyDraft _decodeDraft(Map<String, dynamic> value) {
  _exactKeys(value, const {
    'draft_ref',
    'journey_ref',
    'base_event_head_sha256',
    'kind',
    'payload',
    'payload_sha256',
    'state',
    'updated_at'
  });
  final payload = value['payload'];
  _require(payload is Map<String, dynamic>);
  final state = _parseState(value['state']);
  final updated = DateTime.tryParse(
      value['updated_at'] is String ? value['updated_at'] as String : '');
  _require(updated != null && updated.isUtc);
  final draft = JourneyDraft(
      draftRef: value['draft_ref'] as String,
      journeyRef: value['journey_ref'] as String?,
      baseEventHeadSha256: value['base_event_head_sha256'] as String?,
      kind: value['kind'] as String,
      payload: payload as Map<String, dynamic>,
      state: state,
      updatedAt: updated!);
  _require(value['payload_sha256'] == draft.payloadSha256);
  return draft;
}

Map<String, dynamic> _encodeDraft(JourneyDraft draft) => {
      'base_event_head_sha256': draft.baseEventHeadSha256,
      'draft_ref': draft.draftRef,
      'journey_ref': draft.journeyRef,
      'kind': draft.kind,
      'payload': draft.payload,
      'payload_sha256': draft.payloadSha256,
      'state': draft.state.wire,
      'updated_at': draft.updatedAt.toIso8601String(),
    };

JourneyDraftState _parseState(Object? raw) {
  for (final state in JourneyDraftState.values) {
    if (state.wire == raw) return state;
  }
  throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
}

void _require(bool condition) => condition
    ? null
    : throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);

void _exactKeys(Map<String, dynamic> value, Set<String> expected) =>
    _require(value.keys.toSet().containsAll(expected) &&
        value.length == expected.length);

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

bool _secretKey(String key) => _secretKeyName
    .hasMatch(_decodedText(key).toLowerCase().replaceAll('-', '_'));

bool _safeRef(String value) =>
    _safeRefForm(value) && _safeRefForm(_decodedText(value));
bool _safeRefForm(String value) =>
    value.isNotEmpty &&
    value.length <= 256 &&
    !value.startsWith('/') &&
    !value.startsWith(r'\') &&
    !value.contains(':') &&
    !value.split(RegExp(r'[\\/]')).contains('..');

String _decodedText(String value) {
  final decoded = StringBuffer();
  for (var index = 0; index < value.length;) {
    if (value.codeUnitAt(index) != 0x25) {
      decoded.writeCharCode(value.codeUnitAt(index++));
      continue;
    }
    final next = index + 1 < value.length ? value.codeUnitAt(index + 1) : null;
    if (index + 2 >= value.length ||
        !_hex(next) ||
        !_hex(value.codeUnitAt(index + 2))) {
      _require(next == null || !_asciiAlphaNumeric(next));
      decoded.write('%');
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
      decoded.write(Uri.decodeComponent(value.substring(start, index)));
    } on Object {
      _require(false);
    }
  }
  return decoded.toString();
}

bool _hex(int? value) =>
    value != null &&
    ((value >= 0x30 && value <= 0x39) ||
        (value >= 0x41 && value <= 0x46) ||
        (value >= 0x61 && value <= 0x66));
bool _asciiAlphaNumeric(int value) =>
    (value >= 0x30 && value <= 0x39) ||
    (value >= 0x41 && value <= 0x5a) ||
    (value >= 0x61 && value <= 0x7a);

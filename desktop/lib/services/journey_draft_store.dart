import 'dart:io';

import 'journey_session_store.dart';

export 'journey_session_store.dart'
    show JourneyLocalFailure, JourneyLocalStoreException;

const _draftSchema = 'flywheel.desktop-journey-drafts/v1';
final _draftRef = RegExp(r'^dft_[0-9a-f]{32}$');
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _sha256 = RegExp(r'^[0-9a-f]{64}$');
final _kind = RegExp(r'^[a-z][a-z0-9_]{0,31}$');

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
    final copy = snapshotJourneyLocalJson(payload);
    final request = copy['client_request_id'];
    _require(request is String &&
        request.isNotEmpty &&
        isSafeJourneyLocalText(request));
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
    if (storedRequest != acknowledgement.clientRequestId ||
        !_sha256.hasMatch(acknowledgement.eventHeadSha256)) {
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

void _require(bool condition) {
  if (!condition) {
    throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
  }
}

void _exactKeys(Map<String, dynamic> value, Set<String> expected) =>
    _require(value.keys.toSet().containsAll(expected) &&
        value.length == expected.length);

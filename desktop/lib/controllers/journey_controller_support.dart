part of 'journey_controller.dart';

enum JourneyViewPhase {
  idle,
  loading,
  ready,
  starting,
  appending,
  checking,
  cancelling,
  conflicted,
  blocked,
  failed,
}

enum JourneyRecoveryAction {
  retrySameRequest,
  refreshProjection,
  authenticate,
  updateClient,
  reviewDraft,
  chooseJourney,
}

final class JourneyViewState {
  const JourneyViewState._(this._identity, this._evidence, this._failure);
  final (JourneyViewPhase, JourneyLens, String?, String?) _identity;
  final (
    JourneyProjection?,
    List<JourneySummary>,
    List<JourneyDraft>
  ) _evidence;
  final (
    JourneyFailure?,
    JourneyLocalFailure?,
    Set<JourneyRecoveryAction>,
    JourneyCancelResult?
  ) _failure;
  JourneyViewPhase get phase => _identity.$1;
  JourneyLens get selectedLens => _identity.$2;
  String? get activeJourneyRef => _identity.$3;
  String? get activeOperationRef => _identity.$4;
  JourneyProjection? get projection => _evidence.$1;
  List<JourneySummary> get journeys => _evidence.$2;
  List<JourneyDraft> get drafts => _evidence.$3;
  JourneyFailure? get remoteFailure => _failure.$1;
  JourneyLocalFailure? get localFailure => _failure.$2;
  Set<JourneyRecoveryAction> get recoveryActions => _failure.$3;
  JourneyCancelResult? get cancelResult => _failure.$4;
}

final class JourneyCheckDraft {
  factory JourneyCheckDraft.fromDraft(JourneyDraft draft) {
    const keys = {
      'client_request_id',
      'claim_id',
      'oracle_id',
      'candidate_ref',
      'context_ref'
    };
    final values = draft.payload;
    if (draft.kind != 'check' ||
        draft.journeyRef == null ||
        values.length != keys.length ||
        !values.keys.toSet().containsAll(keys) ||
        values.values.any((value) => value is! String || value.isEmpty)) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
    }
    return JourneyCheckDraft._(draft);
  }
  const JourneyCheckDraft._(this.draft);
  final JourneyDraft draft;
  String get clientRequestId => draft.payload['client_request_id'] as String;
  String get claimId => draft.payload['claim_id'] as String;
  String get oracleId => draft.payload['oracle_id'] as String;
  String get candidateRef => draft.payload['candidate_ref'] as String;
  String get contextRef => draft.payload['context_ref'] as String;
}

enum _M { create, append, check }

final class _View {
  _View(this._notify);
  final VoidCallback _notify;
  var phase = JourneyViewPhase.idle;
  var lens = JourneyLens.verify;
  String? ref, _operation;
  JourneyProjection? projection;
  List<JourneySummary> journeys = const [];
  List<JourneyDraft> _drafts = const [];
  JourneyFailure? remoteFailure;
  JourneyLocalFailure? localFailure;
  Set<JourneyRecoveryAction> recovery = const {};
  JourneyCancelResult? _cancelResult;
  set operation(String? value) => _changed(_operation = value);
  List<JourneyDraft> get drafts => _drafts;
  set drafts(List<JourneyDraft> value) => _changed(_drafts = value);
  JourneyCancelResult? get cancelResult => _cancelResult;
  set cancelResult(JourneyCancelResult? v) => _changed(_cancelResult = v);
  void _changed(Object? _) => _notify();
  JourneyViewState get snapshot => JourneyViewState._(
      (phase, lens, ref, _operation),
      (projection, List.unmodifiable(journeys), List.unmodifiable(drafts)),
      (remoteFailure, localFailure, Set.unmodifiable(recovery), cancelResult));
  void begin(JourneySession? session, List<JourneyDraft> stored) {
    phase = JourneyViewPhase.loading;
    drafts = stored;
    if (session != null) {
      ref = session.journeyRef;
      lens = session.lens;
    }
    _notify();
  }

  void initialized(JourneyProjection? resumed, List<JourneySummary> listed,
      JourneyFailure? failure) {
    projection = resumed;
    journeys = List.unmodifiable(listed);
    remoteFailure = failure;
    localFailure = null;
    phase = resumed != null || ref == null
        ? JourneyViewPhase.ready
        : _failurePhase(failure!);
    recovery = resumed != null ? const {} : _actions(failure);
    _notify();
  }

  void busy(JourneyViewPhase value, {String? operation}) {
    phase = value;
    if (operation != null) _operation = operation;
    _notify();
  }

  void ready(JourneyProjection value, {String? ref, JourneyLens? lens}) {
    projection = value;
    this.ref = ref ?? this.ref;
    this.lens = lens ?? this.lens;
    phase = JourneyViewPhase.ready;
    _clear();
    _notify();
  }

  void remote(JourneyFailure failure) {
    phase = _failurePhase(failure);
    remoteFailure = failure;
    localFailure = null;
    recovery = _actions(failure);
    _notify();
  }

  void local(JourneyLocalFailure failure) {
    phase = JourneyViewPhase.failed;
    localFailure = failure;
    remoteFailure = null;
    recovery = const {JourneyRecoveryAction.reviewDraft};
    _notify();
  }

  void conflict(JourneyFailure failure, JourneyProjection? refreshed) {
    projection = refreshed ?? projection;
    phase = JourneyViewPhase.conflicted;
    remoteFailure = failure;
    recovery = {
      if (refreshed == null) JourneyRecoveryAction.refreshProjection,
      JourneyRecoveryAction.retrySameRequest
    };
    _notify();
  }

  void refreshFailed(JourneyFailure failure) {
    phase = JourneyViewPhase.failed;
    remoteFailure = failure;
    recovery = const {JourneyRecoveryAction.refreshProjection};
    _notify();
  }

  void _clear() {
    remoteFailure = null;
    localFailure = null;
    recovery = const {};
  }
}

final class _Custody {
  const _Custody(this.drafts, this.sessions);
  final JourneyDraftStore drafts;
  final JourneySessionStore sessions;
  JourneySession? get session => sessions.load();
  List<JourneyDraft> list() => drafts.list();
  void save(JourneyDraft draft) => drafts.save(draft);
  void saveSession(String ref, JourneyLens lens) =>
      sessions.save(JourneySession(journeyRef: ref, lens: lens));
  JourneyDraft attempt(JourneyDraft source, _M kind, String? currentHead) {
    if (!_valid(source, kind)) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
    }
    final head =
        kind == _M.create ? null : source.baseEventHeadSha256 ?? currentHead;
    if (kind != _M.create && head == null) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
    }
    final result = _copy(source, head, JourneyDraftState.saving);
    drafts.save(result);
    return result;
  }

  void rebase(JourneyDraft draft, String head) =>
      drafts.save(_copy(draft, head, JourneyDraftState.saveFailed));
  void failed(JourneyDraft draft) => drafts.markFailed(draft.draftRef);
  void delete(JourneyDraft sent, String request, String head) {
    final stored =
        drafts.list().where((item) => item.draftRef == sent.draftRef).single;
    if (stored.payloadSha256 != sent.payloadSha256 ||
        stored.payload['client_request_id'] != request) {
      throw const JourneyLocalStoreException(
          JourneyLocalFailure.acknowledgementMismatch);
    }
    drafts.delete(sent.draftRef,
        acknowledgement: JourneyDraftAcknowledgement(request, head));
  }

  JourneyDraft _copy(
          JourneyDraft draft, String? head, JourneyDraftState state) =>
      JourneyDraft(
          draftRef: draft.draftRef,
          journeyRef: draft.journeyRef,
          baseEventHeadSha256: head,
          kind: draft.kind,
          payload: draft.payload,
          state: state,
          updatedAt: DateTime.now().toUtc());
  bool _valid(JourneyDraft draft, _M kind) {
    final keys = switch (kind) {
      _M.create => const {'client_request_id', 'goal', 'intake_ref'},
      _M.append => const {'client_request_id', 'command'},
      _M.check => const {
          'client_request_id',
          'claim_id',
          'oracle_id',
          'candidate_ref',
          'context_ref'
        },
    };
    if (draft.kind != kind.name ||
        keys.length != draft.payload.length ||
        !draft.payload.keys.toSet().containsAll(keys) ||
        (kind == _M.create
            ? draft.journeyRef != null || draft.baseEventHeadSha256 != null
            : draft.journeyRef == null)) {
      return false;
    }
    return draft.payload.entries.every((entry) => entry.key == 'command'
        ? entry.value is Map<String, dynamic>
        : entry.value is String && (entry.value as String).isNotEmpty);
  }
}

bool _terminal(JourneyCancelResult result, String operation) =>
    !result.invalidResponse &&
    result.operationRef == operation &&
    const {
      JourneyOperationState.cancelled,
      JourneyOperationState.completed,
      JourneyOperationState.failed
    }.contains(result.operationState);
JourneyFailure _invalid() => JourneyFailure(
    'INVALID_RESPONSE', 'Gateway response was invalid', const []);
JourneyFailure _fail(Object e) =>
    e is JourneyApiException ? e.failure : _invalid();
void _accept(bool condition) {
  if (!condition) throw JourneyApiException(_invalid());
}

JourneyViewPhase _failurePhase(JourneyFailure f) => switch (f.code) {
      'HEAD_CONFLICT' => JourneyViewPhase.conflicted,
      'STORE_COMMIT_FAILED' || 'INVALID_RESPONSE' => JourneyViewPhase.failed,
      _ => JourneyViewPhase.blocked,
    };
Set<JourneyRecoveryAction> _actions(JourneyFailure? failure) =>
    switch (failure?.code) {
      'AUTH_REQUIRED' => const {
          JourneyRecoveryAction.authenticate,
          JourneyRecoveryAction.retrySameRequest
        },
      'VERSION_MISMATCH' => const {JourneyRecoveryAction.updateClient},
      'STORE_COMMIT_FAILED' => const {
          JourneyRecoveryAction.retrySameRequest,
          JourneyRecoveryAction.reviewDraft
        },
      'IDEMPOTENCY_MISMATCH' => const {JourneyRecoveryAction.reviewDraft},
      'JOURNEY_NOT_FOUND' => const {JourneyRecoveryAction.chooseJourney},
      'CANCEL_UNAVAILABLE' => const {JourneyRecoveryAction.refreshProjection},
      'STORE_BUSY' ||
      'PERMISSION_REQUIRED' ||
      'APPROVAL_EXPIRED' ||
      'INVALID_RESPONSE' ||
      'HEAD_CONFLICT' =>
        const {JourneyRecoveryAction.retrySameRequest},
      _ => const {},
    };

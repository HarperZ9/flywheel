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

const _retry = JourneyRecoveryAction.retrySameRequest;
const _refresh = JourneyRecoveryAction.refreshProjection;
const _auth = JourneyRecoveryAction.authenticate;
const _review = JourneyRecoveryAction.reviewDraft;
const _reviewOnly = {_review};
const _acknowledgedActions = {_review, _refresh};
typedef JourneyViewState = ({
  JourneyViewPhase phase,
  JourneyLens selectedLens,
  String? activeJourneyRef,
  String? activeOperationRef,
  JourneyProjection? projection,
  List<JourneySummary> journeys,
  List<JourneyDraft> drafts,
  JourneyFailure? remoteFailure,
  JourneyLocalFailure? localFailure,
  Set<JourneyRecoveryAction> recoveryActions,
  JourneyCancelResult? cancelResult,
});
extension type const JourneyCheckDraft._(JourneyDraft draft) {
  factory JourneyCheckDraft.fromDraft(JourneyDraft draft) {
    _validLocal(_validDraft(draft, _M.check));
    return JourneyCheckDraft._(draft);
  }
  String get clientRequestId => draft.payload['client_request_id'] as String;
  String get claimId => draft.payload['claim_id'] as String;
  String get oracleId => draft.payload['oracle_id'] as String;
  String get candidateRef => draft.payload['candidate_ref'] as String;
  String get contextRef => draft.payload['context_ref'] as String;
}

enum _M { create, append, check }

typedef _Target = ({int epoch, String? ref, JourneyLens lens});
typedef _Ack = ({int generation, String ref, String head});
String _t(JourneyDraft draft, String key) => draft.payload[key] as String;

final class _Acks {
  final Map<String, _Ack> _v = {};
  var _g = 0;
  _Ack add(String r, String h) => _v[r] = (generation: ++_g, ref: r, head: h);
  _Ack? forRef(String r) => _v[r];
  bool take(_Ack a) => _v[a.ref] == a && _v.remove(a.ref) != null;
}

final class _View {
  _View(this._notify);
  final VoidCallback _notify;
  var phase = JourneyViewPhase.idle;
  var lens = JourneyLens.verify;
  String? ref, _operation;
  JourneyProjection? projection;
  List<JourneySummary> journeys = const [];
  List<JourneyDraft> _drafts = const [];
  (JourneyFailure?, JourneyLocalFailure?, Set<JourneyRecoveryAction>) errors =
      (null, null, const {});
  JourneyCancelResult? _cancelResult;
  set operation(String? value) => _changed(_operation = value);
  List<JourneyDraft> get drafts => _drafts;
  set drafts(List<JourneyDraft> value) => _changed(_drafts = value);
  JourneyCancelResult? get cancelResult => _cancelResult;
  set cancelResult(JourneyCancelResult? v) => _changed(_cancelResult = v);
  void _changed(Object? _) => _notify();
  bool hasRef(String? v) => v != null && projection?.journeyRef == v;
  JourneyViewState get snapshot => (
        phase: phase,
        selectedLens: lens,
        activeJourneyRef: ref,
        activeOperationRef: _operation,
        projection: projection?.journeyRef == ref ? projection : null,
        journeys: List.unmodifiable(journeys),
        drafts: List.unmodifiable(drafts),
        remoteFailure: errors.$1,
        localFailure: errors.$2,
        recoveryActions: Set.unmodifiable(errors.$3),
        cancelResult: cancelResult,
      );
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
    _accept(resumed == null || resumed.journeyRef == ref);
    projection = resumed;
    journeys = List.unmodifiable(listed);
    phase = resumed != null || ref == null
        ? JourneyViewPhase.ready
        : _failurePhase(failure!);
    errors = (failure, null, resumed != null ? const {} : _actions(failure));
    _notify();
  }

  void busy(JourneyViewPhase value, {String? operation}) {
    phase = value;
    if (operation != null) _operation = operation;
    _notify();
  }

  void ready(JourneyProjection value, {String? ref, JourneyLens? lens}) {
    final nextRef = ref ?? this.ref;
    _accept(nextRef != null && value.journeyRef == nextRef);
    _bind(nextRef!);
    projection = value;
    this.lens = lens ?? this.lens;
    phase = JourneyViewPhase.ready;
    errors = (null, null, const {});
    _notify();
  }

  void remote(JourneyFailure failure,
      {JourneyViewPhase? phase, Set<JourneyRecoveryAction>? actions}) {
    this.phase = phase ?? _failurePhase(failure);
    errors = (failure, null, actions ?? _actions(failure));
    _notify();
  }

  void local(JourneyLocalFailure failure, {bool acknowledged = false}) {
    phase = JourneyViewPhase.failed;
    errors = (null, failure, acknowledged ? _acknowledgedActions : _reviewOnly);
    _notify();
  }

  void acknowledgedRef(String value) => _changed(_bind(value));

  void conflict(JourneyFailure failure, JourneyProjection? refreshed) {
    _accept(refreshed == null || refreshed.journeyRef == ref);
    projection = refreshed ?? projection;
    phase = JourneyViewPhase.conflicted;
    errors = (failure, null, {if (refreshed == null) _refresh, _retry});
    _notify();
  }

  void refreshFailed(JourneyFailure failure) => remote(failure,
      phase: JourneyViewPhase.failed, actions: const {_refresh});

  String _bind(String value) {
    if (value == ref) return value;
    ref = value;
    projection = null;
    _operation = null;
    _cancelResult = null;
    return value;
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
    _validLocal(_validDraft(source, kind));
    final head = kind == _M.create
        ? null
        : switch (source.state) {
            JourneyDraftState.saving ||
            JourneyDraftState.saveFailed ||
            JourneyDraftState.recoveryAvailable =>
              source.baseEventHeadSha256,
            _ => currentHead,
          };
    _validLocal(kind == _M.create || head != null);
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
    _validLocal(
        stored.payloadSha256 == sent.payloadSha256 &&
            stored.payload['client_request_id'] == request,
        JourneyLocalFailure.acknowledgementMismatch);
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
}

void _validLocal(bool valid,
        [JourneyLocalFailure failure = JourneyLocalFailure.invalidRecord]) =>
    valid ? null : throw JourneyLocalStoreException(failure);

bool _validDraft(JourneyDraft draft, _M kind) {
  final expected = switch (kind) {
    _M.create => 'client_request_id|goal|intake_ref',
    _M.append => 'client_request_id|command',
    _M.check =>
      'candidate_ref|claim_id|client_request_id|context_ref|oracle_id',
  };
  return draft.kind == kind.name &&
      (kind == _M.create
          ? draft.journeyRef == null && draft.baseEventHeadSha256 == null
          : draft.journeyRef != null) &&
      expected.split('|').length == draft.payload.length &&
      expected.split('|').every(draft.payload.containsKey) &&
      draft.payload.entries.every((entry) => entry.key == 'command'
          ? entry.value is Map<String, dynamic>
          : entry.value is String && (entry.value as String).isNotEmpty);
}

bool _terminal(JourneyCancelResult result, String operation) =>
    !result.invalidResponse &&
    result.operationRef == operation &&
    const {'cancelled', 'completed', 'failed'}
        .contains(result.operationState.name);
bool _validAck(JourneyMutationAck ack, _M kind, String? operation) =>
    !ack.invalidResponse &&
    switch (kind) {
      _M.check => ack.operationRef == operation &&
          ack.operationState != null &&
          ack.operationState != JourneyOperationState.unknown,
      _ => ack.operationRef == null && ack.operationState == null,
    };
Future<JourneyProjection> _resume(
    (JourneyApi, String, JourneyLens) input) async {
  final result = await input.$1.resume(input.$2, input.$3);
  _accept(!result.invalidResponse &&
      result.journeyRef == input.$2 &&
      result.lens == input.$3);
  return result;
}

JourneyFailure _invalid() => JourneyFailure(
    'INVALID_RESPONSE', 'Gateway response was invalid', const []);
JourneyFailure _fail(Object e) =>
    e is JourneyApiException ? e.failure : _invalid();
void _accept(bool condition) =>
    condition ? null : throw JourneyApiException(_invalid());
JourneyViewPhase _failurePhase(JourneyFailure f) => switch (f.code) {
      'HEAD_CONFLICT' => JourneyViewPhase.conflicted,
      'STORE_COMMIT_FAILED' || 'INVALID_RESPONSE' => JourneyViewPhase.failed,
      _ => JourneyViewPhase.blocked,
    };
Set<JourneyRecoveryAction> _actions(JourneyFailure? failure) =>
    switch (failure?.code) {
      'AUTH_REQUIRED' => const {_auth, _retry},
      'VERSION_MISMATCH' => const {JourneyRecoveryAction.updateClient},
      'STORE_COMMIT_FAILED' => const {_retry, _review},
      'IDEMPOTENCY_MISMATCH' => const {_review},
      'JOURNEY_NOT_FOUND' => const {JourneyRecoveryAction.chooseJourney},
      'CANCEL_UNAVAILABLE' => const {_refresh},
      'STORE_BUSY' ||
      'PERMISSION_REQUIRED' ||
      'APPROVAL_EXPIRED' ||
      'INVALID_RESPONSE' ||
      'HEAD_CONFLICT' =>
        const {_retry},
      _ => const {},
    };

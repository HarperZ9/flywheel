import 'package:flutter/foundation.dart';
import '../client/journey_api.dart';
import '../models/journey_models.dart';
import '../services/journey_draft_store.dart';
import '../services/journey_session_store.dart';
part 'journey_controller_support.dart';
part 'journey_controller_refresh.dart';
part 'journey_controller_cancel.dart';

final class JourneyController extends ChangeNotifier {
  JourneyController({
    required JourneyApi api,
    required JourneyDraftStore draftStore,
    required JourneySessionStore sessionStore,
  })  : _api = api,
        _custody = _Custody(draftStore, sessionStore);
  final JourneyApi _api;
  late final _View _view = _View(notifyListeners);
  final _Custody _custody;
  Future<void> _tail = Future.value();
  final Map<String, String> _cancelHeads = {};
  final _Acks _acks = _Acks();
  _Target? _desired;
  var _epoch = 0;
  JourneyViewState get state => _view.snapshot;
  Future<void> initialize() async {
    final epoch = ++_epoch;
    JourneySession? session;
    try {
      session = _custody.session;
      _view.begin(session, _custody.list());
    } on JourneyLocalStoreException catch (error) {
      _view.local(error.failure);
      return;
    }
    JourneyProjection? resumed;
    JourneyFailure? failure;
    if (session != null) {
      try {
        resumed = await _resume((_api, session.journeyRef, session.lens));
      } on Object catch (error) {
        failure = _fail(error);
      }
    }
    List<JourneySummary> listed = const [];
    try {
      listed = await _api.list();
      _accept(!listed.any((item) => item.invalidResponse));
    } on Object catch (error) {
      failure ??= _fail(error);
    }
    if (epoch != _epoch) return;
    _view.initialized(resumed, listed, failure);
  }

  Future<void> _select(String ref, JourneyLens lens, bool same) async {
    final intent = _desired = (epoch: ++_epoch, ref: ref, lens: lens);
    final prior = _view.projection;
    _view.busy(JourneyViewPhase.loading);
    try {
      final result = await _resume((_api, ref, lens));
      if (intent != _desired) return;
      final ack = _acks.forRef(ref);
      final exact = ack != null && result.eventHeadSha256 == ack.head;
      _accept(!same || exact || result.sameEvidenceAs(prior!));
      _custody.saveSession(ref, lens);
      _view.ready(result, ref: ref, lens: lens);
      _desired = null;
      if (exact) _acks.take(ack);
      if (!exact && ack != null) await _refreshAck(ack, intent.lens);
    } on JourneyLocalStoreException catch (error) {
      if (intent != _desired) return;
      _desired = null;
      final ack = _acks.forRef(ref);
      _view.local(error.failure, acknowledged: ack != null && _acks.take(ack));
    } on Object catch (error) {
      if (intent != _desired) return;
      _desired = null;
      final ack = _acks.forRef(ref);
      if (ack != null && _acks.take(ack)) {
        _view.refreshFailed(_fail(error));
      } else {
        _view.remote(_fail(error));
      }
    }
  }

  void saveDraft(JourneyDraft draft) {
    try {
      _custody.save(draft);
      _view.drafts = _custody.list();
    } on JourneyLocalStoreException catch (error) {
      _view.local(error.failure);
    }
  }

  Future<void> submitStart(JourneyDraft d) => _q(() => _run(d, _M.create));
  Future<void> submitAppend(JourneyDraft d) => _q(() => _run(d, _M.append));
  Future<void> runCheck(JourneyCheckDraft d) =>
      _q(() => _run(d.draft, _M.check));
  Future<void> requestCancel(String ref) => _q(() => _cancel(ref));

  /// Switch to a journey picked from the sessions view and make it current,
  /// reusing the same resume-and-persist path as launch, so a session started on
  /// one device reopens on another that points at the same gateway.
  Future<void> openSession(String ref, JourneyLens lens) =>
      _q(() => _select(ref, lens, false));

  Future<void> _run(JourneyDraft source, _M kind) async {
    final target = _capture();
    _view.busy(JourneyViewPhase.values[kind.index + 3]);
    late JourneyDraft draft;
    try {
      _validLocal(kind == _M.create || _view.hasRef(source.journeyRef));
      draft = _custody.attempt(source, kind, _view.projection?.eventHeadSha256);
      _view.drafts = _custody.list();
      final granted = await _grant(_intent(draft, kind), kind.name);
      if (_view.ref == target.ref) _view.operation = granted.$2;
      final ack = await _send(draft, kind, granted.$1);
      final ref = kind == _M.create ? ack.journeyRef : draft.journeyRef;
      _accept(ack.journeyRef == ref && _validAck(ack, kind, granted.$2));
      final token = _acks.add(ref!, ack.eventHeadSha256);
      await _afterAck(draft, target, token);
    } on JourneyLocalStoreException catch (error) {
      if (_current(target)) _view.local(error.failure);
    } on Object catch (error) {
      final failure = _fail(error);
      if (failure.code == 'HEAD_CONFLICT' && kind != _M.create) {
        await _conflict(failure, target, draft: draft);
      } else {
        _failDraft(draft, failure, target);
      }
    }
  }

  Future<void> _afterAck(JourneyDraft draft, _Target initial, _Ack ack) async {
    JourneyLocalFailure? e;
    try {
      if (draft.journeyRef == null && _current(initial)) {
        _view.acknowledgedRef(ack.ref);
        _custody.saveSession(ack.ref, initial.lens);
      }
      _custody.delete(draft, _t(draft, 'client_request_id'), ack.head);
      _view.drafts = _custody.list();
    } on JourneyLocalStoreException catch (error) {
      e = error.failure;
    }
    await _refreshAck(ack, initial.lens);
    if (e != null && _view.ref == ack.ref) _view.local(e, acknowledged: true);
  }

  GrantIntent _intent(JourneyDraft draft, _M kind) {
    final value = draft.payload;
    return switch (kind) {
      _M.create => GrantIntent.create(
          goal: _t(draft, 'goal'),
          intakeRef: _t(draft, 'intake_ref'),
          clientRequestId: _t(draft, 'client_request_id')),
      _M.append => GrantIntent.append(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: _t(draft, 'client_request_id'),
          command: value['command'] as Map<String, dynamic>),
      _M.check => GrantIntent.check(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: _t(draft, 'client_request_id'),
          claimId: _t(draft, 'claim_id'),
          oracleId: _t(draft, 'oracle_id'),
          candidateRef: _t(draft, 'candidate_ref'),
          contextRef: _t(draft, 'context_ref')),
    };
  }

  Future<JourneyMutationAck> _send(JourneyDraft draft, _M kind, String grant) {
    final value = draft.payload;
    return switch (kind) {
      _M.create => _api.create(JourneyCreateRequest(
          goal: _t(draft, 'goal'),
          intakeRef: _t(draft, 'intake_ref'),
          clientRequestId: _t(draft, 'client_request_id'),
          grantRef: grant)),
      _M.append => _api.append(JourneyAppendRequest(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: _t(draft, 'client_request_id'),
          grantRef: grant,
          command: value['command'] as Map<String, dynamic>)),
      _M.check => _api.check(JourneyCheckRequest(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: _t(draft, 'client_request_id'),
          grantRef: grant,
          claimId: _t(draft, 'claim_id'),
          oracleId: _t(draft, 'oracle_id'),
          candidateRef: _t(draft, 'candidate_ref'),
          contextRef: _t(draft, 'context_ref'))),
    };
  }

  Future<(String, String?)> _grant(GrantIntent intent, String action) async {
    final p = await _api.prepareGrant(intent);
    _accept(!p.invalidResponse &&
        p.action == action &&
        ((p.operationRef != null) == (action == 'check')));
    final g = await _api.approveGrantOnce(p.proposalRef);
    _accept(!g.invalidResponse && g.grantRef == p.plannedGrantRef);
    return (g.grantRef, p.operationRef);
  }

  Future<void> _refreshAck(_Ack token, JourneyLens fallback) async {
    final (selectionEpoch, desired) = (_epoch, _desired);
    if (desired?.ref == token.ref) return;
    final active = (desired?.ref ?? _view.ref) == token.ref;
    final lens = active ? _view.lens : fallback;
    JourneyProjection? refreshed;
    JourneyFailure? failure;
    try {
      refreshed = await _resume((_api, token.ref, lens));
    } on Object catch (e) {
      failure = _fail(e);
    }
    if (selectionEpoch != _epoch || !_acks.take(token) || !active) return;
    if (failure != null) return _view.refreshFailed(failure);
    _view.ready(refreshed!);
  }

  Future<void> _conflict(JourneyFailure failure, _Target target,
      {JourneyDraft? draft, String? operation}) async {
    try {
      final ref = draft?.journeyRef ?? target.ref!;
      final refreshed = await _resume((_api, ref, target.lens));
      if (draft != null) {
        _custody.rebase(draft, refreshed.eventHeadSha256);
        _view.drafts = _custody.list();
      } else {
        _cancelHeads['$ref:${operation!}'] = refreshed.eventHeadSha256;
      }
      if (_current(target)) _view.conflict(failure, refreshed);
    } on JourneyLocalStoreException catch (error) {
      if (_current(target)) _view.local(error.failure);
    } on Object {
      if (_current(target)) _view.conflict(failure, null);
    }
  }

  void _failDraft(JourneyDraft draft, JourneyFailure failure, _Target target) {
    try {
      _custody.failed(draft);
      _view.drafts = _custody.list();
      if (_current(target)) _view.remote(failure);
    } on JourneyLocalStoreException catch (error) {
      if (_current(target)) _view.local(error.failure);
    }
  }

  _Target _capture() => (epoch: _epoch, ref: _view.ref, lens: _view.lens);
  bool _current(_Target target) => target == _capture();
  Future<void> _q(Future<void> Function() action) => _tail = _tail
      .then((_) => action())
      .then<void>((_) {}, onError: (_) => _view.remote(_invalid()));
}

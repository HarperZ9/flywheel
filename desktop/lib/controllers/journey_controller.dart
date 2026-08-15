import 'package:flutter/foundation.dart';
import '../client/journey_api.dart';
import '../models/journey_models.dart';
import '../services/journey_draft_store.dart';
import '../services/journey_session_store.dart';
part 'journey_controller_support.dart';

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
  _Target? _desired;
  String? _pendingAck;
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

  Future<void> selectJourney(String ref) => _select(ref, _view.lens, false);
  Future<void> selectLens(JourneyLens lens) async {
    if (!_view.canSelect || lens == JourneyLens.invalidResponse) {
      _view.remote(_invalid());
      return;
    }
    await _select(_view.ref!, lens, true);
  }

  Future<void> _select(String ref, JourneyLens lens, bool same) async {
    final intent = _desired = (epoch: ++_epoch, ref: ref, lens: lens);
    final prior = _view.projection;
    _view.busy(JourneyViewPhase.loading);
    try {
      final result = await _resume((_api, ref, lens));
      if (intent != _desired) return;
      _accept(!same || result.sameEvidenceAs(prior!));
      _custody.saveSession(ref, lens);
      _view.ready(result, ref: ref, lens: lens);
      if (_pendingAck == ref) await _refreshAcknowledged(ref, intent);
    } on JourneyLocalStoreException catch (error) {
      if (intent == _desired) _view.local(error.failure);
    } on Object catch (error) {
      if (intent == _desired) _view.remote(_fail(error));
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
  Future<void> _run(JourneyDraft source, _M kind) async {
    if (kind != _M.create && !_view.hasRef(source.journeyRef)) {
      _view.local(JourneyLocalFailure.invalidRecord);
      return;
    }
    final target = _capture();
    _view.busy(JourneyViewPhase.values[kind.index + 3]);
    late JourneyDraft draft;
    try {
      draft = _custody.attempt(source, kind, _view.projection?.eventHeadSha256);
      _view.drafts = _custody.list();
      final request = draft.payload['client_request_id'] as String;
      final granted = await _grant(_intent(draft, kind), kind.name);
      if (_view.ref == target.ref) _view.operation = granted.$2;
      final ack = await _dispatch(draft, kind, granted.$1);
      final ref = kind == _M.create ? ack.journeyRef : draft.journeyRef;
      _accept(ack.journeyRef == ref && _validAck(ack, kind, granted.$2));
      await _acknowledged(draft, kind, ack, request, target);
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

  Future<void> _acknowledged(JourneyDraft draft, _M kind,
      JourneyMutationAck ack, String request, _Target initial) async {
    JourneyLocalFailure? e;
    var t = initial;
    try {
      if (kind == _M.create) {
        t = (epoch: initial.epoch, ref: ack.journeyRef, lens: initial.lens);
        if (_current(initial)) {
          _view.acknowledgedRef(ack.journeyRef);
          _custody.saveSession(ack.journeyRef, t.lens);
        }
      }
      _custody.delete(draft, request, ack.eventHeadSha256);
      _view.drafts = _custody.list();
    } on JourneyLocalStoreException catch (error) {
      e = error.failure;
    }
    await _refreshAcknowledged(ack.journeyRef, t);
    if (e != null && _view.ref == t.ref) _view.local(e, acknowledged: true);
  }

  GrantIntent _intent(JourneyDraft draft, _M kind) {
    final value = draft.payload;
    String text(String key) => value[key] as String;
    return switch (kind) {
      _M.create => GrantIntent.create(
          goal: text('goal'),
          intakeRef: text('intake_ref'),
          clientRequestId: text('client_request_id')),
      _M.append => GrantIntent.append(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: text('client_request_id'),
          command: value['command'] as Map<String, dynamic>),
      _M.check => GrantIntent.check(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: text('client_request_id'),
          claimId: text('claim_id'),
          oracleId: text('oracle_id'),
          candidateRef: text('candidate_ref'),
          contextRef: text('context_ref')),
    };
  }

  Future<JourneyMutationAck> _dispatch(
      JourneyDraft draft, _M kind, String grant) {
    final value = draft.payload;
    String text(String key) => value[key] as String;
    return switch (kind) {
      _M.create => _api.create(JourneyCreateRequest(
          goal: text('goal'),
          intakeRef: text('intake_ref'),
          clientRequestId: text('client_request_id'),
          grantRef: grant)),
      _M.append => _api.append(JourneyAppendRequest(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: text('client_request_id'),
          grantRef: grant,
          command: value['command'] as Map<String, dynamic>)),
      _M.check => _api.check(JourneyCheckRequest(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: text('client_request_id'),
          grantRef: grant,
          claimId: text('claim_id'),
          oracleId: text('oracle_id'),
          candidateRef: text('candidate_ref'),
          contextRef: text('context_ref'))),
    };
  }

  Future<void> _cancel(String operation) async {
    final current = _view.projection;
    if (current == null || !operationRefPattern.hasMatch(operation)) {
      _view.remote(_invalid());
      return;
    }
    final target = _capture();
    _view.busy(JourneyViewPhase.cancelling, operation: operation);
    _view.cancelResult = null;
    final key = '${current.journeyRef}:$operation';
    final head = _cancelHeads.putIfAbsent(key, () => current.eventHeadSha256);
    try {
      final request = 'cancel:$operation';
      final granted = await _grant(
          GrantIntent.cancel(
              journeyRef: current.journeyRef,
              expectedEventHead: head,
              clientRequestId: request,
              operationRef: operation),
          'cancel');
      final result = await _api.cancel(JourneyCancelRequest(
          journeyRef: current.journeyRef,
          expectedEventHead: head,
          clientRequestId: request,
          grantRef: granted.$1,
          operationRef: operation));
      _accept(_terminal(result, operation));
      _cancelHeads.remove(key);
      if (_view.ref == current.journeyRef) _view.cancelResult = result;
      await _refreshAcknowledged(current.journeyRef, target);
    } on Object catch (error) {
      final failure = _fail(error);
      if (failure.code == 'HEAD_CONFLICT') {
        await _conflict(failure, target, operation: operation);
      } else if (_current(target)) {
        _view.remote(failure);
      }
    }
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

  Future<void> _refreshAcknowledged(String ref, _Target target) async {
    _pendingAck = ref;
    final desired = _desired;
    if (_view.phase == JourneyViewPhase.loading && desired?.ref == ref) return;
    final active = (desired?.ref ?? _view.ref) == ref;
    final lens = active ? desired?.lens ?? _view.lens : target.lens;
    try {
      final refreshed = await _resume((_api, ref, lens));
      _pendingAck = null;
      if (active && desired == _desired) _view.ready(refreshed);
    } on Object catch (e) {
      _pendingAck = null;
      if (active && desired == _desired) _view.refreshFailed(_fail(e));
    }
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
  Future<void> _q(Future<void> Function() action) {
    final result = _tail.then((_) => action());
    _tail = result.then<void>((_) {}, onError: (_) {});
    return result;
  }
}

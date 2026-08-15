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
  _View? _model;
  _View get _view => _model ??= _View(notifyListeners);
  final _Custody _custody;
  Future<void> _tail = Future.value();
  final Map<String, String> _cancelHeads = {};
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
        resumed = await _resume(session.journeyRef, session.lens);
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
    if (_view.projection == null ||
        _view.ref == null ||
        lens == JourneyLens.invalidResponse) {
      _view.remote(_invalid());
      return;
    }
    await _select(_view.ref!, lens, true);
  }

  Future<void> _select(String ref, JourneyLens lens, bool same) async {
    final epoch = ++_epoch, prior = _view.projection;
    _view.busy(JourneyViewPhase.loading);
    try {
      final result = await _resume(ref, lens);
      if (epoch != _epoch) return;
      _accept(!same || result.sameEvidenceAs(prior!));
      _custody.saveSession(ref, lens);
      _view.ready(result, ref: ref, lens: lens);
    } on JourneyLocalStoreException catch (error) {
      if (epoch == _epoch) _view.local(error.failure);
    } on Object catch (error) {
      if (epoch == _epoch) _view.remote(_fail(error));
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
    if (kind != _M.create &&
        (_view.projection == null ||
            source.journeyRef != _view.projection!.journeyRef)) {
      _view.local(JourneyLocalFailure.invalidRecord);
      return;
    }
    ++_epoch;
    _view.busy(JourneyViewPhase.values[kind.index + 3]);
    JourneyDraft draft;
    try {
      draft = _custody.attempt(source, kind, _view.projection?.eventHeadSha256);
      _view.drafts = _custody.list();
    } on JourneyLocalStoreException catch (error) {
      _view.local(error.failure);
      return;
    }
    try {
      final request = draft.payload['client_request_id'] as String;
      final granted = await _grant(_intent(draft, kind), kind.name);
      _view.operation = granted.$2;
      final ack = await _dispatch(draft, kind, granted.$1);
      final ref = kind == _M.create ? ack.journeyRef : draft.journeyRef;
      _accept(!ack.invalidResponse &&
          ack.journeyRef == ref &&
          (kind == _M.check
              ? ack.operationRef == granted.$2
              : ack.operationRef == null));
      _custody.delete(draft, request, ack.eventHeadSha256);
      _view.drafts = _custody.list();
      if (kind == _M.create) {
        _view.ref = ack.journeyRef;
        _custody.saveSession(ack.journeyRef, _view.lens);
      }
      await _refreshAcknowledged(ack.journeyRef);
    } on JourneyLocalStoreException catch (error) {
      _view.local(error.failure);
    } on Object catch (error) {
      final failure = _fail(error);
      if (failure.code == 'HEAD_CONFLICT' && kind != _M.create) {
        await _conflict(failure, draft: draft);
      } else {
        _failDraft(draft, failure);
      }
    }
  }

  GrantIntent _intent(JourneyDraft draft, _M kind) {
    final value = draft.payload;
    String text(String key) => value[key] as String;
    final request = text('client_request_id');
    return switch (kind) {
      _M.create => GrantIntent.create(
          goal: text('goal'),
          intakeRef: text('intake_ref'),
          clientRequestId: request),
      _M.append => GrantIntent.append(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: request,
          command: value['command'] as Map<String, dynamic>),
      _M.check => GrantIntent.check(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: request,
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
    final request = text('client_request_id');
    if (kind == _M.create) {
      return _api.create(JourneyCreateRequest(
          goal: text('goal'),
          intakeRef: text('intake_ref'),
          clientRequestId: request,
          grantRef: grant));
    }
    if (kind == _M.append) {
      return _api.append(JourneyAppendRequest(
          journeyRef: draft.journeyRef!,
          expectedEventHead: draft.baseEventHeadSha256!,
          clientRequestId: request,
          grantRef: grant,
          command: value['command'] as Map<String, dynamic>));
    }
    return _api.check(JourneyCheckRequest(
        journeyRef: draft.journeyRef!,
        expectedEventHead: draft.baseEventHeadSha256!,
        clientRequestId: request,
        grantRef: grant,
        claimId: text('claim_id'),
        oracleId: text('oracle_id'),
        candidateRef: text('candidate_ref'),
        contextRef: text('context_ref')));
  }

  Future<void> _cancel(String operation) async {
    final current = _view.projection;
    if (current == null || !operationRefPattern.hasMatch(operation)) {
      _view.remote(_invalid());
      return;
    }
    ++_epoch;
    _view.busy(JourneyViewPhase.cancelling, operation: operation);
    _view.cancelResult = null;
    final head =
        _cancelHeads.putIfAbsent(operation, () => current.eventHeadSha256);
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
      _cancelHeads.remove(operation);
      _view.cancelResult = result;
      await _refreshAcknowledged(current.journeyRef);
    } on Object catch (error) {
      final failure = _fail(error);
      if (failure.code == 'HEAD_CONFLICT') {
        await _conflict(failure, operation: operation);
      } else {
        _view.remote(failure);
      }
    }
  }

  Future<(String, String?)> _grant(GrantIntent intent, String action) async {
    final proposal = await _api.prepareGrant(intent);
    _accept(!proposal.invalidResponse &&
        proposal.action == action &&
        ((proposal.operationRef != null) == (action == 'check')));
    final grant = await _api.approveGrantOnce(proposal.proposalRef);
    _accept(
        !grant.invalidResponse && grant.grantRef == proposal.plannedGrantRef);
    return (grant.grantRef, proposal.operationRef);
  }

  Future<JourneyProjection> _resume(String ref, JourneyLens lens) async {
    final result = await _api.resume(ref, lens);
    _accept(!result.invalidResponse &&
        result.journeyRef == ref &&
        result.lens == lens);
    return result;
  }

  Future<void> _refreshAcknowledged(String ref) async {
    try {
      _view.ready(await _resume(ref, _view.lens), ref: ref);
    } on Object catch (error) {
      _view.refreshFailed(_fail(error));
    }
  }

  Future<void> _conflict(JourneyFailure failure,
      {JourneyDraft? draft, String? operation}) async {
    try {
      final ref = draft?.journeyRef ?? _view.ref!;
      final refreshed = await _resume(ref, _view.lens);
      if (draft != null) {
        _custody.rebase(draft, refreshed.eventHeadSha256);
        _view.drafts = _custody.list();
      } else {
        _cancelHeads[operation!] = refreshed.eventHeadSha256;
      }
      _view.conflict(failure, refreshed);
    } on JourneyLocalStoreException catch (error) {
      _view.local(error.failure);
    } on Object {
      _view.conflict(failure, null);
    }
  }

  void _failDraft(JourneyDraft draft, JourneyFailure failure) {
    try {
      _custody.failed(draft);
      _view.drafts = _custody.list();
      _view.remote(failure);
    } on JourneyLocalStoreException catch (error) {
      _view.local(error.failure);
    }
  }

  Future<void> _q(Future<void> Function() action) {
    final result = _tail.then((_) => action());
    _tail = result.then<void>((_) {}, onError: (_) {});
    return result;
  }
}

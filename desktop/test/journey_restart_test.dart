import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'journey_controller_test.dart';

JourneyCancelResult _cancelResult({String state = 'cancelled'}) =>
    JourneyCancelResult.fromJson({
      'operation_ref': operationA,
      'state': state,
      'event_head_sha256': headB,
      'terminal_event_ref': headB,
    });
void main() {
  _restartTests();
  _readTests();
  _retryTests();
  _ackTests();
  _grantTests();
  _failureTests();
}

void _restartTests() {
  test('startup restores exact session and drafts independent of list failure',
      () async {
    final api = ScriptedJourneyApi();
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append', baseHead: headA);
    harness.drafts.save(item);
    harness.sessions
        .save(JourneySession(journeyRef: journeyA, lens: JourneyLens.diagnose));
    api
      ..reply(
          'resume:$journeyA:diagnose', projection(lens: JourneyLens.diagnose))
      ..reply(
          'list',
          JourneyApiException(JourneyFailure(
              'STORE_BUSY', 'Journey persistence is busy', const [])));
    await harness.controller.initialize();
    expect(harness.controller.state.activeJourneyRef, journeyA);
    expect(harness.controller.state.selectedLens, JourneyLens.diagnose);
    expect(harness.controller.state.projection?.journeyRef, journeyA);
    expect(harness.controller.state.drafts.single.payloadSha256,
        item.payloadSha256);
  });
  test('create ack persists session and a new controller resumes it', () async {
    final api = ScriptedJourneyApi();
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    final item = draft('create');
    harness.controller.saveDraft(item);
    api
      ..reply('prepare', proposal('create'))
      ..reply('approve', approval())
      ..reply('create', acknowledgement())
      ..reply('resume:$journeyA:verify', projection(head: headB));
    await harness.controller.submitStart(item);
    expect(harness.drafts.list(), isEmpty);
    expect(harness.sessions.load()?.journeyRef, journeyA);
    final request = api.createRequests.single;
    expect([request.clientRequestId, request.goal, request.intakeRef],
        ['request-create', 'Preserve evidence', 'intake.json']);
    final restartApi = ScriptedJourneyApi()
      ..reply('resume:$journeyA:verify', projection(head: headB))
      ..reply('list', <JourneySummary>[projection(head: headB)]);
    final restarted = JourneyController(
        api: restartApi,
        draftStore: harness.drafts,
        sessionStore: harness.sessions);
    await restarted.initialize();
    expect(restarted.state.projection?.eventHeadSha256, headB);
  });
}

void _readTests() {
  test('lens accepts equal evidence and rejects wrong ref or core drift',
      () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    api.reply(
        'resume:$journeyA:diagnose', projection(lens: JourneyLens.diagnose));
    await harness.controller.selectLens(JourneyLens.diagnose);
    expect(harness.controller.state.selectedLens, JourneyLens.diagnose);
    expect(harness.sessions.load()?.lens, JourneyLens.diagnose);
    api.reply('resume:$journeyA:rescue',
        projection(journeyRef: journeyB, lens: JourneyLens.rescue));
    await harness.controller.selectLens(JourneyLens.rescue);
    expect(harness.controller.state.phase, JourneyViewPhase.failed);
    expect(harness.controller.state.selectedLens, JourneyLens.diagnose);
    api.reply('resume:$journeyA:rescue',
        projection(lens: JourneyLens.rescue, fact: 'changed'));
    await harness.controller.selectLens(JourneyLens.rescue);
    expect(harness.controller.state.selectedLens, JourneyLens.diagnose);
  });
  test('newer Journey selection wins over an older resume response', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final older = Completer<JourneyProjection>();
    api
      ..reply('resume:$journeyA:verify', older.future)
      ..reply('resume:$journeyB:verify', projection(journeyRef: journeyB));
    final first = harness.controller.selectJourney(journeyA);
    final second = harness.controller.selectJourney(journeyB);
    await second;
    older.complete(projection());
    await first;
    expect(harness.controller.state.activeJourneyRef, journeyB);
    expect(harness.controller.state.projection?.journeyRef, journeyB);
  });
}

void _retryTests() {
  test('restart retry preserves request and attempted head', () async {
    final firstApi = ScriptedJourneyApi();
    final harness = await readyHarness(firstApi);
    addTearDown(harness.dispose);
    final item = draft('append');
    harness.controller.saveDraft(item);
    firstApi.reply(
        'prepare',
        JourneyApiException(JourneyFailure(
            'STORE_BUSY', 'Journey persistence is busy', const [])));
    await harness.controller.submitAppend(item);
    final retained = harness.drafts.list().single;
    expect(retained.baseEventHeadSha256, headA);
    expect(retained.state, JourneyDraftState.saveFailed);
    final retryApi = ScriptedJourneyApi()
      ..reply('resume:$journeyA:verify', projection(head: headB))
      ..reply('list', <JourneySummary>[projection(head: headB)])
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply('append', acknowledgement())
      ..reply('resume:$journeyA:verify', projection(head: headB));
    final restarted = JourneyController(
        api: retryApi,
        draftStore: harness.drafts,
        sessionStore: harness.sessions);
    await restarted.initialize();
    await restarted.submitAppend(restarted.state.drafts.single);
    expect(retryApi.appendRequests.single.expectedEventHead, headA);
    expect(retryApi.appendRequests.single.clientRequestId, 'request-append');
  });
  test('head conflict rebases retained draft without deletion', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append');
    harness.controller.saveDraft(item);
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply(
          'append',
          JourneyApiException(JourneyFailure(
              'HEAD_CONFLICT', 'Journey state changed', const [])))
      ..reply('resume:$journeyA:verify', projection(head: headB));
    await harness.controller.submitAppend(item);
    final retained = harness.drafts.list().single;
    expect(retained.baseEventHeadSha256, headB);
    expect(retained.payload['client_request_id'], 'request-append');
    expect(harness.controller.state.phase, JourneyViewPhase.conflicted);
    expect(harness.controller.state.recoveryActions,
        {JourneyRecoveryAction.retrySameRequest});
  });
}

void _ackTests() {
  test('edited draft survives ack and terminal cancel uses exact result',
      () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append');
    harness.controller.saveDraft(item);
    final pending = Completer<JourneyMutationAck>();
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply('append', pending.future);
    final submit = harness.controller.submitAppend(item);
    while (api.appendRequests.isEmpty) {
      await Future<void>.delayed(Duration.zero);
    }
    harness.drafts.save(JourneyDraft(
      draftRef: item.draftRef,
      journeyRef: journeyA,
      baseEventHeadSha256: headA,
      kind: 'append',
      payload: {
        ...item.payload,
        'command': {'kind': 'changed'}
      },
      state: JourneyDraftState.dirty,
      updatedAt: DateTime.utc(2026, 8, 15, 1),
    ));
    api.reply('resume:$journeyA:verify', projection(head: headB));
    pending.complete(acknowledgement());
    await submit;
    expect(harness.drafts.list(), hasLength(1));
    await harness.controller.requestCancel('not-an-operation-ref');
    expect(
        api.calls, ['prepare', 'approve', 'append', 'resume:$journeyA:verify']);
    api
      ..reply('prepare', proposal('cancel'))
      ..reply('approve', approval())
      ..reply('cancel', _cancelResult())
      ..reply('resume:$journeyA:verify', projection(head: headB));
    await harness.controller.requestCancel(operationA);
    expect(harness.controller.state.cancelResult?.operationState,
        JourneyOperationState.cancelled);
    expect(api.cancelRequests.single.clientRequestId, 'cancel:$operationA');
    api.reply('resume:$journeyA:diagnose',
        projection(head: headB, lens: JourneyLens.diagnose));
    await harness.controller.selectLens(JourneyLens.diagnose);
    expect(harness.controller.state.activeOperationRef, operationA);
    expect(harness.controller.state.cancelResult, isNotNull);
    api
      ..reply('prepare', proposal('cancel'))
      ..reply('approve', approval())
      ..reply('cancel', _cancelResult(state: 'running'));
    await harness.controller.requestCancel(operationA);
    expect(harness.controller.state.remoteFailure?.code, 'INVALID_RESPONSE');
    expect(harness.controller.state.cancelResult, isNull);
  });
}

void _grantTests() {
  test('grant and acknowledgement mismatches retain the exact draft', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    harness.controller.saveDraft(draft('append'));
    api.reply('prepare', proposal('check', operationRef: operationA));
    await harness.controller.submitAppend(harness.drafts.list().single);
    expect(api.appendRequests, isEmpty);
    const otherGrant = 'gnt_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval(grantRef: otherGrant));
    await harness.controller.submitAppend(harness.drafts.list().single);
    expect(api.appendRequests, isEmpty);
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply('append', acknowledgement(journeyRef: journeyB));
    await harness.controller.submitAppend(harness.drafts.list().single);
    expect(harness.drafts.list(), hasLength(1));
    expect(harness.controller.state.remoteFailure?.code, 'INVALID_RESPONSE');
  });
}

void _failureTests() {
  test('fixed remote failures expose exact recovery actions', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    harness.controller.saveDraft(draft('append'));
    const retry = {JourneyRecoveryAction.retrySameRequest};
    const review = {JourneyRecoveryAction.reviewDraft};
    const update = {JourneyRecoveryAction.updateClient};
    const choose = {JourneyRecoveryAction.chooseJourney};
    const refresh = {JourneyRecoveryAction.refreshProjection};
    const retryReview = {
      JourneyRecoveryAction.retrySameRequest,
      JourneyRecoveryAction.reviewDraft
    };
    final cases = <String, (JourneyViewPhase, Set<JourneyRecoveryAction>)>{
      'VERSION_MISMATCH': (JourneyViewPhase.blocked, update),
      'STORE_COMMIT_FAILED': (JourneyViewPhase.failed, retryReview),
      'PERMISSION_REQUIRED': (JourneyViewPhase.blocked, retry),
      'APPROVAL_EXPIRED': (JourneyViewPhase.blocked, retry),
      'IDEMPOTENCY_MISMATCH': (JourneyViewPhase.blocked, review),
      'JOURNEY_NOT_FOUND': (JourneyViewPhase.blocked, choose),
      'CANCEL_UNAVAILABLE': (JourneyViewPhase.blocked, refresh),
      'INVALID_RESPONSE': (JourneyViewPhase.failed, retry),
    };
    final preserved = harness.controller.state.projection;
    for (final entry in cases.entries) {
      final failure = JourneyFailure(entry.key, 'Fixed detail', const []);
      api.reply('prepare', JourneyApiException(failure));
      await harness.controller.submitAppend(harness.drafts.list().single);
      expect(harness.controller.state.phase, entry.value.$1);
      expect(harness.controller.state.recoveryActions, entry.value.$2);
      expect(identical(harness.controller.state.projection, preserved), isTrue);
    }
  });
}

import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'journey_controller_test.dart';

const journeyB = 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const diag = JourneyLens.diagnose;
const resumeB = 'resume:$journeyB:verify';
const resumeDiag = 'resume:$journeyA:diagnose';
const writeFailed = JourneyLocalFailure.writeFailed;
const review = JourneyRecoveryAction.reviewDraft;
const refresh = JourneyRecoveryAction.refreshProjection;
const ackRecovery = {review, refresh};
Never failWrite() => throw const JourneyLocalStoreException(writeFailed);
JourneyCancelResult cancelResult({String state = 'cancelled'}) =>
    JourneyCancelResult.fromJson({
      'operation_ref': operationA,
      'state': state,
      'event_head_sha256': headB,
      'terminal_event_ref': headB,
    });
JourneyController _restart(ControllerHarness h, ScriptedJourneyApi api) =>
    JourneyController(api: api, draftStore: h.drafts, sessionStore: h.sessions);
void main() {
  _restartTests();
  _readTests();
  _retryTests();
  _ackTests();
  _grantTests();
}

void _restartTests() {
  test('startup restores session/drafts despite list failure', () async {
    final api = ScriptedJourneyApi();
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append', baseHead: headA);
    harness.drafts.save(item);
    harness.sessions.save(JourneySession(journeyRef: journeyA, lens: diag));
    api
      ..reply(resumeDiag, projection(lens: diag))
      ..reply('list', failure('STORE_BUSY'));
    await harness.controller.initialize();
    expect(harness.controller.state.activeJourneyRef, journeyA);
    expect(harness.controller.state.selectedLens, diag);
    expect(harness.controller.state.projection?.journeyRef, journeyA);
    expect(harness.controller.state.drafts.single.payloadSha256,
        item.payloadSha256);
  });
  test('create ack persists session and a new controller resumes it', () async {
    final api = ScriptedJourneyApi();
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    final item = harness.save(draft('create'));
    api
      ..mutation('create', acknowledgement())
      ..reply(resumeA, projection(head: headB));
    await harness.controller.submitStart(item);
    expect(harness.drafts.list(), isEmpty);
    expect(harness.sessions.load()?.journeyRef, journeyA);
    final request = api.createRequests.single;
    expect([request.clientRequestId, request.goal, request.intakeRef],
        ['request-create', 'Preserve evidence', 'intake.json']);
    final restartApi = ScriptedJourneyApi()
      ..reply(resumeA, projection(head: headB))
      ..reply('list', <JourneySummary>[projection(head: headB)]);
    final restarted = _restart(harness, restartApi);
    await restarted.initialize();
    expect(restarted.state.projection?.eventHeadSha256, headB);
  });
  for (final failedSelection in const [false, true]) {
    final state = failedSelection ? 'failed' : 'completed';
    test('create after $state selection',
        () => _createAfterSelection(failedSelection));
  }
}

Future<void> _createAfterSelection(bool failed) async {
  final (api, harness) = await ready();
  api.reply(resumeDiag,
      failed ? failure('INVALID_RESPONSE') : projection(lens: diag));
  await harness.controller.selectLens(diag);
  final lens = failed ? JourneyLens.verify : diag;
  final item = harness.save(draft('create'));
  api
    ..mutation('create', acknowledgement(journeyRef: journeyB))
    ..reply('resume:$journeyB:${lens.name}',
        projection(journeyRef: journeyB, head: headB, lens: lens));
  await harness.controller.submitStart(item);
  final view = harness.controller.state;
  expect([view.phase, view.activeJourneyRef, view.projection?.journeyRef],
      [JourneyViewPhase.ready, journeyB, journeyB]);
  expect(harness.sessions.load()?.journeyRef, journeyB);
  expect(harness.drafts.list(), isEmpty);
}

void _readTests() {
  test('lens accepts equal evidence and rejects drift', () async {
    final (api, harness) = await ready();
    api.reply(resumeDiag, projection(lens: diag));
    await harness.controller.selectLens(diag);
    expect(harness.controller.state.selectedLens, diag);
    expect(harness.sessions.load()?.lens, diag);
    api.reply('resume:$journeyA:rescue',
        projection(journeyRef: journeyB, lens: JourneyLens.rescue));
    await harness.controller.selectLens(JourneyLens.rescue);
    expect(harness.controller.state.phase, JourneyViewPhase.failed);
    expect(harness.controller.state.selectedLens, diag);
    api.reply('resume:$journeyA:rescue',
        projection(lens: JourneyLens.rescue, fact: 'changed'));
    await harness.controller.selectLens(JourneyLens.rescue);
    expect(harness.controller.state.selectedLens, diag);
  });
  test('newer Journey selection wins over an older resume response', () async {
    final (api, harness) = await ready();
    final older = Completer<JourneyProjection>();
    api
      ..reply(resumeA, older.future)
      ..reply(resumeB, projection(journeyRef: journeyB));
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
    final (firstApi, harness) = await ready();
    final item = harness.save(draft('append'));
    firstApi.reply('prepare', failure('STORE_BUSY'));
    await harness.controller.submitAppend(item);
    final retained = harness.drafts.list().single;
    expect(retained.baseEventHeadSha256, headA);
    expect(retained.state, JourneyDraftState.saveFailed);
    final retryApi = ScriptedJourneyApi()
      ..reply(resumeA, projection(head: headB))
      ..reply('list', <JourneySummary>[projection(head: headB)])
      ..mutation('append', acknowledgement())
      ..reply(resumeA, projection(head: headB));
    final restarted = _restart(harness, retryApi);
    await restarted.initialize();
    await restarted.submitAppend(restarted.state.drafts.single);
    expect(retryApi.appendRequests.single.expectedEventHead, headA);
    expect(retryApi.appendRequests.single.clientRequestId, 'request-append');
  });
  test('head conflict rebases retained draft without deletion', () async {
    final (api, harness) = await ready();
    final item = harness.save(draft('append'));
    api
      ..mutation('append', failure('HEAD_CONFLICT'))
      ..reply(resumeA, projection(head: headB));
    await harness.controller.submitAppend(item);
    final retained = harness.drafts.list().single;
    expect(retained.baseEventHeadSha256, headB);
    expect(retained.payload['client_request_id'], 'request-append');
    expect(harness.controller.state.phase, JourneyViewPhase.conflicted);
    expect(harness.controller.state.recoveryActions,
        {JourneyRecoveryAction.retrySameRequest});
  });
  test('dirty draft uses current head, not stale base', () async {
    final (api, harness) = await ready();
    final item = harness.save(draft('append', baseHead: headB));
    api.mutation('append', failure('STORE_BUSY'));
    await harness.controller.submitAppend(item);
    expect(api.appendRequests.single.expectedEventHead, headA);
    expect(harness.drafts.list().single.baseEventHeadSha256, headA);
  });
}

void _ackTests() {
  test('edited draft survives ack and cancel stays exact', () async {
    final (api, harness) = await ready();
    final item = harness.save(draft('append'));
    final pending = Completer<JourneyMutationAck>();
    api.mutation('append', pending.future);
    final submit = harness.controller.submitAppend(item);
    while (api.appendRequests.isEmpty) {
      await Future<void>.delayed(Duration.zero);
    }
    harness.drafts.save(edited(item));
    api.reply(resumeA, projection(head: headB));
    pending.complete(acknowledgement());
    await submit;
    expect(harness.drafts.list(), hasLength(1));
    await harness.controller.requestCancel('not-an-operation-ref');
    expect(api.calls, ['prepare', 'approve', 'append', resumeA]);
    api
      ..mutation('cancel', cancelResult())
      ..reply(resumeA, projection(head: headB));
    await harness.controller.requestCancel(operationA);
    expect(harness.controller.state.cancelResult?.operationState,
        JourneyOperationState.cancelled);
    expect(api.cancelRequests.single.clientRequestId, 'cancel:$operationA');
    api.reply(resumeDiag, projection(head: headB, lens: diag));
    await harness.controller.selectLens(diag);
    expect(harness.controller.state.activeOperationRef, operationA);
    expect(harness.controller.state.cancelResult, isNotNull);
    api.mutation('cancel', cancelResult(state: 'running'));
    await harness.controller.requestCancel(operationA);
    expect(harness.controller.state.remoteFailure?.code, 'INVALID_RESPONSE');
    expect(harness.controller.state.cancelResult, isNull);
  });
  for (final kind in const ['append', 'check']) {
    test('$kind ack refresh failure does not replay',
        () => _ackRefreshRestart(kind));
  }
}

Future<void> _ackRefreshRestart(String kind) async {
  final (api, harness) = await ready();
  final item = harness.save(draft(kind));
  api
    ..mutation(kind,
        acknowledgement(operationRef: kind == 'check' ? operationA : null),
        operationRef: kind == 'check' ? operationA : null)
    ..reply(resumeA, failure('STORE_BUSY'));
  await harness.submit(kind, item);
  expect(harness.drafts.list(), isEmpty);
  expect(harness.controller.state.recoveryActions,
      {JourneyRecoveryAction.refreshProjection});
  final restartApi = ScriptedJourneyApi()
    ..reply(resumeA, projection(head: headB))
    ..reply('list', <JourneySummary>[projection(head: headB)]);
  final restarted = _restart(harness, restartApi);
  await restarted.initialize();
  expect(restarted.state.projection?.eventHeadSha256, headB);
  expect(restarted.state.drafts, isEmpty);
}

void _grantTests() {
  test('check draft rejects delimiter-collided exact field names', () {
    final collided = draft('check',
        ref: 'dft_cccccccccccccccccccccccccccccccc',
        payload: const {
          'candidate_ref|claim_id': 'candidate.py',
          'client_request_id': 'request-collision',
          'context_ref': 'context.json',
          'oracle_id': 'code'
        });
    expect(() => JourneyCheckDraft.fromDraft(collided),
        throwsA(isA<JourneyLocalStoreException>()));
  });
  test('grant/ack mismatches retain the draft', () async {
    final (api, harness) = await ready();
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
    api.mutation('append', acknowledgement(journeyRef: journeyB));
    await harness.controller.submitAppend(harness.drafts.list().single);
    expect(harness.drafts.list(), hasLength(1));
    expect(harness.controller.state.remoteFailure?.code, 'INVALID_RESPONSE');
  });
  test('fixed remote failures expose exact recovery actions', () async {
    final (api, harness) = await ready();
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
      api.reply('prepare', failure(entry.key));
      await harness.controller.submitAppend(harness.drafts.list().single);
      expect(harness.controller.state.phase, entry.value.$1);
      expect(harness.controller.state.recoveryActions, entry.value.$2);
      expect(identical(harness.controller.state.projection, preserved), isTrue);
    }
  });
}

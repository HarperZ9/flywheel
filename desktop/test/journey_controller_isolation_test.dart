import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';

import 'journey_controller_test.dart';

JourneyCancelResult _cancelResult() => JourneyCancelResult.fromJson({
      'operation_ref': operationA,
      'state': 'cancelled',
      'event_head_sha256': headB,
      'terminal_event_ref': headB,
    });

void main() {
  _raceTests();
  _custodyTests();
  _exactKeyTests();
  _contractTests();
}

void _exactKeyTests() {
  test('check draft rejects delimiter-collided exact field names', () {
    final collided = JourneyDraft(
        draftRef: 'dft_cccccccccccccccccccccccccccccccc',
        journeyRef: journeyA,
        kind: 'check',
        payload: const {
          'candidate_ref|claim_id': 'candidate.py',
          'client_request_id': 'request-collision',
          'context_ref': 'context.json',
          'oracle_id': 'code'
        },
        state: JourneyDraftState.dirty,
        updatedAt: DateTime.utc(2026, 8, 15));
    expect(() => JourneyCheckDraft.fromDraft(collided),
        throwsA(isA<JourneyLocalStoreException>()));
  });
}

void _raceTests() {
  test('append acknowledgement cannot overwrite a newer Journey', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append');
    harness.controller.saveDraft(item);
    final pending = Completer<JourneyMutationAck>();
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply('append', pending.future)
      ..reply('resume:$journeyB:verify', projection(journeyRef: journeyB))
      ..reply('resume:$journeyA:verify', projection(head: headB));
    final submitted = harness.controller.submitAppend(item);
    while (api.appendRequests.isEmpty) {
      await Future<void>.delayed(Duration.zero);
    }
    await harness.controller.selectJourney(journeyB);
    pending.complete(acknowledgement());
    await submitted;
    final state = harness.controller.state;
    expect(state.activeJourneyRef, journeyB);
    expect(state.projection?.journeyRef, journeyB);
  });

  test('conflict refresh cannot mix a newer ref with older evidence', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append');
    harness.controller.saveDraft(item);
    final pending = Completer<JourneyMutationAck>();
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply('append', pending.future)
      ..reply('resume:$journeyB:verify', projection(journeyRef: journeyB))
      ..reply('resume:$journeyA:verify', projection(head: headB));
    final submitted = harness.controller.submitAppend(item);
    while (api.appendRequests.isEmpty) {
      await Future<void>.delayed(Duration.zero);
    }
    await harness.controller.selectJourney(journeyB);
    pending.completeError(JourneyApiException(
        JourneyFailure('HEAD_CONFLICT', 'Journey state changed', const [])));
    await submitted;
    final state = harness.controller.state;
    expect(state.activeJourneyRef, journeyB);
    expect(state.projection?.journeyRef, journeyB);
  });

  test('cancel cannot overwrite a newer Journey and switching clears result',
      () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final pending = Completer<JourneyCancelResult>();
    api
      ..reply('prepare', proposal('cancel'))
      ..reply('approve', approval())
      ..reply('cancel', pending.future)
      ..reply('resume:$journeyB:verify', projection(journeyRef: journeyB))
      ..reply('resume:$journeyA:verify', projection(head: headB));
    final cancelled = harness.controller.requestCancel(operationA);
    while (api.cancelRequests.isEmpty) {
      await Future<void>.delayed(Duration.zero);
    }
    await harness.controller.selectJourney(journeyB);
    pending.complete(_cancelResult());
    await cancelled;
    final state = harness.controller.state;
    expect(state.activeJourneyRef, journeyB);
    expect(state.projection?.journeyRef, journeyB);
    expect(state.activeOperationRef, isNull);
    expect(state.cancelResult, isNull);
  });
}

void _custodyTests() {
  test('durable ack refreshes even when edited draft cannot be deleted',
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
      ..reply('append', pending.future)
      ..reply('resume:$journeyA:verify', projection(head: headB));
    final submitted = harness.controller.submitAppend(item);
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
        updatedAt: DateTime.utc(2026, 8, 15, 1)));
    pending.complete(acknowledgement());
    await submitted;
    expect(api.calls.last, 'resume:$journeyA:verify');
    expect(harness.controller.state.projection?.eventHeadSha256, headB);
    expect(harness.drafts.list(), hasLength(1));
    expect(harness.controller.state.recoveryActions, {
      JourneyRecoveryAction.reviewDraft,
      JourneyRecoveryAction.refreshProjection
    });
  });

  test('create ack remains visible and refreshes after session write failure',
      () async {
    final api = ScriptedJourneyApi();
    final harness = ControllerHarness(api,
        sessionBeforeRename: (_) => throw const JourneyLocalStoreException(
            JourneyLocalFailure.writeFailed));
    addTearDown(harness.dispose);
    final item = draft('create');
    harness.controller.saveDraft(item);
    api
      ..reply('prepare', proposal('create'))
      ..reply('approve', approval())
      ..reply('create', acknowledgement())
      ..reply('resume:$journeyA:verify', projection(head: headB));
    await harness.controller.submitStart(item);
    final state = harness.controller.state;
    expect(api.calls.last, 'resume:$journeyA:verify');
    expect(state.activeJourneyRef, journeyA);
    expect(state.projection?.eventHeadSha256, headB);
    expect(state.localFailure, JourneyLocalFailure.writeFailed);
    expect(state.recoveryActions, {
      JourneyRecoveryAction.reviewDraft,
      JourneyRecoveryAction.refreshProjection
    });
  });
}

void _contractTests() {
  test('check wrapper and view collections fail closed and immutable', () {
    final valid = draft('check');
    expect(JourneyCheckDraft.fromDraft(valid).clientRequestId, 'request-check');
    expect(
      () => JourneyCheckDraft.fromDraft(JourneyDraft(
        draftRef: valid.draftRef,
        journeyRef: journeyA,
        kind: 'check',
        payload: {...valid.payload, 'extra': 'value'},
        state: JourneyDraftState.dirty,
        updatedAt: valid.updatedAt,
      )),
      throwsA(isA<JourneyLocalStoreException>()),
    );
    final harness = ControllerHarness(ScriptedJourneyApi());
    addTearDown(harness.dispose);
    final state = harness.controller.state;
    expect(() => state.drafts.add(valid), throwsUnsupportedError);
    expect(() => state.recoveryActions.add(JourneyRecoveryAction.reviewDraft),
        throwsUnsupportedError);
  });

  test('fresh dirty draft uses current head instead of stale stored base',
      () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append', baseHead: headB);
    harness.controller.saveDraft(item);
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply(
          'append',
          JourneyApiException(JourneyFailure(
              'STORE_BUSY', 'Journey persistence is busy', const [])));
    await harness.controller.submitAppend(item);
    expect(api.appendRequests.single.expectedEventHead, headA);
    expect(harness.drafts.list().single.baseEventHeadSha256, headA);
  });

  test('ack context rejects missing or unexplained operation state', () async {
    Future<void> rejects(String kind, JourneyMutationAck ack) async {
      final api = ScriptedJourneyApi();
      final harness = await readyHarness(api);
      addTearDown(harness.dispose);
      final item = draft(kind);
      harness.controller.saveDraft(item);
      api
        ..reply('prepare',
            proposal(kind, operationRef: kind == 'check' ? operationA : null))
        ..reply('approve', approval())
        ..reply(kind, ack);
      if (kind == 'check') {
        await harness.controller.runCheck(JourneyCheckDraft.fromDraft(item));
      } else {
        await harness.controller.submitAppend(item);
      }
      expect(harness.controller.state.remoteFailure?.code, 'INVALID_RESPONSE');
      expect(harness.drafts.list(), hasLength(1));
    }

    await rejects(
        'check',
        acknowledgement(
            operationRef: operationA, includeOperationState: false));
    await rejects('check',
        acknowledgement(operationRef: operationA, operationState: 'unknown'));
    await rejects('append', acknowledgement(operationState: 'completed'));
  });
}

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
  for (final ackFirst in const [false, true]) {
    for (final kind in const ['append', 'check', 'cancel']) {
      final order = ackFirst ? 'pending selection' : 'selected lens';
      test('$kind completion refreshes the $order',
          () => _sameJourneyLensRace(kind, ackFirst));
    }
  }
  _custodyTests();
  _exactKeyTests();
  _contractTests();
}

Future<void> _sameJourneyLensRace(String kind, bool ackFirst) async {
  final api = ScriptedJourneyApi();
  final harness = await readyHarness(api);
  addTearDown(harness.dispose);
  final item = draft(kind == 'cancel' ? 'append' : kind);
  if (kind != 'cancel') harness.controller.saveDraft(item);
  final mutation = Completer<JourneyMutationAck>();
  final cancellation = Completer<JourneyCancelResult>();
  final selection = Completer<JourneyProjection>();
  api
    ..reply('prepare',
        proposal(kind, operationRef: kind == 'check' ? operationA : null))
    ..reply('approve', approval())
    ..reply(kind, kind == 'cancel' ? cancellation.future : mutation.future)
    ..reply('resume:$journeyA:diagnose',
        ackFirst ? selection.future : projection(lens: JourneyLens.diagnose))
    ..reply('resume:$journeyA:diagnose',
        projection(head: headB, lens: JourneyLens.diagnose));
  final submitted = switch (kind) {
    'append' => harness.controller.submitAppend(item),
    'check' => harness.controller.runCheck(JourneyCheckDraft.fromDraft(item)),
    _ => harness.controller.requestCancel(operationA),
  };
  await api.waitFor(kind);
  final selected = harness.controller.selectLens(JourneyLens.diagnose);
  if (!ackFirst) await selected;
  if (kind == 'cancel') {
    cancellation.complete(_cancelResult());
  } else {
    mutation.complete(
        acknowledgement(operationRef: kind == 'check' ? operationA : null));
  }
  await submitted;
  if (ackFirst) {
    selection.complete(projection(lens: JourneyLens.diagnose));
    await selected;
  }
  final state = harness.controller.state;
  expect([state.activeJourneyRef, state.projection?.journeyRef],
      [journeyA, journeyA]);
  expect(state.selectedLens, JourneyLens.diagnose);
  expect(state.projection?.eventHeadSha256, headB);
  expect(api.calls.where((call) => call.endsWith(':diagnose')), hasLength(2));
  if (kind == 'cancel') {
    expect(state.cancelResult?.operationState, JourneyOperationState.cancelled);
  } else {
    expect(harness.drafts.list(), isEmpty);
  }
}

void _raceTests() {
  test('append acknowledgement cannot overwrite a newer Journey',
      () => _crossJourneyRace('append', false));
  test('conflict refresh cannot mix a newer ref with older evidence',
      () => _crossJourneyRace('conflict', false));
  test('cancel cannot overwrite a newer Journey and switching clears result',
      () => _crossJourneyRace('cancel', false));
  test('append completion preserves a pending Journey selection',
      () => _crossJourneyRace('append', true));
}

Future<void> _crossJourneyRace(String outcome, bool pendingSelection) async {
  final api = ScriptedJourneyApi();
  final harness = await readyHarness(api);
  addTearDown(harness.dispose);
  final action = outcome == 'cancel' ? 'cancel' : 'append';
  final item = draft('append');
  if (action == 'append') harness.controller.saveDraft(item);
  final mutation = Completer<JourneyMutationAck>();
  final cancellation = Completer<JourneyCancelResult>();
  final selection = Completer<JourneyProjection>();
  api
    ..reply('prepare', proposal(action))
    ..reply('approve', approval())
    ..reply(action, action == 'cancel' ? cancellation.future : mutation.future)
    ..reply('resume:$journeyB:verify',
        pendingSelection ? selection.future : projection(journeyRef: journeyB))
    ..reply('resume:$journeyA:verify', projection(head: headB));
  final submitted = action == 'cancel'
      ? harness.controller.requestCancel(operationA)
      : harness.controller.submitAppend(item);
  await api.waitFor(action);
  final selected = harness.controller.selectJourney(journeyB);
  if (!pendingSelection) await selected;
  if (outcome == 'conflict') {
    mutation.completeError(JourneyApiException(
        JourneyFailure('HEAD_CONFLICT', 'Journey state changed', const [])));
  } else if (action == 'cancel') {
    cancellation.complete(_cancelResult());
  } else {
    mutation.complete(acknowledgement());
  }
  await submitted;
  if (pendingSelection) {
    selection.complete(projection(journeyRef: journeyB));
    await selected;
  }
  final state = harness.controller.state;
  expect([state.activeJourneyRef, state.projection?.journeyRef],
      [journeyB, journeyB]);
  if (action == 'cancel') {
    expect([state.activeOperationRef, state.cancelResult], [null, null]);
  }
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
    await api.waitFor('append');
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

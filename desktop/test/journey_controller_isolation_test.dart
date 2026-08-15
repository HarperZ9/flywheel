import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';

import 'journey_controller_test.dart';
import 'journey_restart_test.dart';

void main() {
  _raceTests();
  test('ack generations are conditionally consumed', _ackGenerationRace);
  test('selection retains an in-flight acknowledgement', _ackSelectionRace);
  _custodyTests();
  _modelContractTests();
}

void _raceTests() {
  for (final kind in const ['append', 'check', 'cancel']) {
    test('$kind refreshes a pre-ack delayed selection',
        () => _sameJourneyRace(kind, 'pre'));
    test('$kind accepts an exact post-ack delayed selection',
        () => _sameJourneyRace(kind, 'exact'));
    for (final result in const ['error', 'malformed']) {
      test('$kind $result selection after ack is refresh-only',
          () => _sameJourneyRace(kind, result));
    }
  }
  for (final kind in const ['append', 'check', 'cancel']) {
    test('$kind cannot overwrite a completed Journey selection',
        () => _crossJourneyRace(kind, false));
    test('$kind cannot overwrite a pending Journey selection',
        () => _crossJourneyRace(kind, true));
  }
  test('conflict refresh cannot mix a newer ref with older evidence',
      () => _crossJourneyRace('conflict', false));
}

Future<void> _sameJourneyRace(String kind, String result) async {
  final (api, harness) = await ready();
  final item = draft(kind == 'cancel' ? 'append' : kind);
  if (kind != 'cancel') harness.controller.saveDraft(item);
  final mutation = Completer<JourneyMutationAck>();
  final cancellation = Completer<JourneyCancelResult>();
  final selection = Completer<JourneyProjection>();
  api
    ..mutation(kind, kind == 'cancel' ? cancellation.future : mutation.future,
        operationRef: kind == 'check' ? operationA : null)
    ..reply('resume:$journeyA:diagnose', selection.future);
  if (result == 'pre') {
    api.reply('resume:$journeyA:diagnose',
        projection(head: headB, lens: JourneyLens.diagnose));
  }
  final submitted = harness.submit(kind, item);
  await api.waitFor(kind);
  final selected = harness.controller.selectLens(JourneyLens.diagnose);
  if (kind == 'cancel') {
    cancellation.complete(cancelResult());
  } else {
    mutation.complete(
        acknowledgement(operationRef: kind == 'check' ? operationA : null));
  }
  await submitted;
  switch (result) {
    case 'pre':
      selection.complete(projection(lens: JourneyLens.diagnose));
    case 'exact':
      selection.complete(projection(head: headB, lens: JourneyLens.diagnose));
    case 'malformed':
      selection.complete(JourneyProjection.fromJson(const {}));
    default:
      selection.completeError(Exception('transport unavailable'));
  }
  await selected;
  final state = harness.controller.state;
  expect([state.activeJourneyRef, state.projection?.journeyRef],
      [journeyA, journeyA]);
  if (const {'error', 'malformed'}.contains(result)) {
    expect(state.phase, JourneyViewPhase.failed);
    expect(state.recoveryActions, {JourneyRecoveryAction.refreshProjection});
  } else {
    expect([state.selectedLens, state.projection?.eventHeadSha256],
        [JourneyLens.diagnose, headB]);
    expect(api.calls.where((call) => call.endsWith(':diagnose')),
        hasLength(result == 'pre' ? 2 : 1));
  }
  if (kind != 'cancel') expect(harness.drafts.list(), isEmpty);
}

Future<void> _crossJourneyRace(String kind, bool pendingSelection) async {
  final (api, harness) = await ready();
  final action = kind == 'conflict' ? 'append' : kind;
  final item = draft(action == 'cancel' ? 'append' : action);
  if (action != 'cancel') harness.controller.saveDraft(item);
  final mutation = Completer<JourneyMutationAck>();
  final cancellation = Completer<JourneyCancelResult>();
  final selection = Completer<JourneyProjection>();
  api
    ..mutation(
        action, action == 'cancel' ? cancellation.future : mutation.future,
        operationRef: action == 'check' ? operationA : null)
    ..reply('resume:$journeyB:verify',
        pendingSelection ? selection.future : projection(journeyRef: journeyB))
    ..reply('resume:$journeyA:verify', projection(head: headB));
  final submitted = harness.submit(action, item);
  await api.waitFor(action);
  final selected = harness.controller.selectJourney(journeyB);
  if (!pendingSelection) await selected;
  if (kind == 'conflict') {
    mutation.completeError(failure('HEAD_CONFLICT'));
  } else if (action == 'cancel') {
    cancellation.complete(cancelResult());
  } else {
    mutation.complete(
        acknowledgement(operationRef: action == 'check' ? operationA : null));
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

Future<void> _ackGenerationRace() async {
  final (api, harness) = await ready();
  final first = harness.save(draft('append'));
  final second = harness
      .save(draft('append', ref: 'dft_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
  final ack1 = Completer<JourneyMutationAck>();
  final selection = Completer<JourneyProjection>();
  final oldRefresh = Completer<JourneyProjection>();
  api
    ..mutation('append', ack1.future)
    ..reply('resume:$journeyA:diagnose', selection.future)
    ..reply('resume:$journeyA:diagnose', oldRefresh.future)
    ..reply('resume:$journeyA:diagnose',
        projection(head: headC, lens: JourneyLens.diagnose));
  final one = harness.controller.submitAppend(first);
  await api.waitFor('append');
  final selected = harness.controller.selectLens(JourneyLens.diagnose);
  ack1.complete(acknowledgement());
  await one;
  selection.complete(projection(lens: JourneyLens.diagnose));
  while (api.calls.where((c) => c.endsWith(':diagnose')).length < 2) {
    await Future<void>.delayed(Duration.zero);
  }
  api.mutation('append', acknowledgement(head: headC));
  await harness.controller.submitAppend(second);
  oldRefresh.complete(projection(head: headB, lens: JourneyLens.diagnose));
  await selected;
  expect(harness.controller.state.projection?.eventHeadSha256, headC);
  expect(harness.drafts.list(), isEmpty);
}

Future<void> _ackSelectionRace() async {
  final (api, harness) = await ready();
  final item = harness.save(draft('append'));
  final refresh = Completer<JourneyProjection>();
  final selection = Completer<JourneyProjection>();
  api
    ..mutation('append', acknowledgement())
    ..reply('resume:$journeyA:verify', refresh.future)
    ..reply('resume:$journeyA:diagnose', selection.future)
    ..reply('resume:$journeyA:diagnose',
        projection(head: headB, lens: JourneyLens.diagnose));
  final submitted = harness.controller.submitAppend(item);
  await api.waitFor('resume:$journeyA:verify');
  final selected = harness.controller.selectLens(JourneyLens.diagnose);
  refresh.complete(projection(head: headB));
  await submitted;
  selection.complete(projection(lens: JourneyLens.diagnose));
  await selected;
  expect(harness.controller.state.projection?.eventHeadSha256, headB);
  expect(api.calls.where((call) => call.endsWith(':diagnose')), hasLength(2));
}

void _custodyTests() {
  test('durable ack refreshes even when edited draft cannot be deleted',
      () async {
    final (api, harness) = await ready();
    final item = harness.save(draft('append'));
    final pending = Completer<JourneyMutationAck>();
    api
      ..mutation('append', pending.future)
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
    final item = harness.save(draft('create'));
    api
      ..mutation('create', acknowledgement())
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

void _modelContractTests() {
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

  test('ack context rejects missing or unexplained operation state', () async {
    Future<void> rejects(String kind, JourneyMutationAck ack) async {
      final (api, harness) = await ready();
      final item = harness.save(draft(kind));
      api.mutation(kind, ack,
          operationRef: kind == 'check' ? operationA : null);
      await harness.submit(kind, item);
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

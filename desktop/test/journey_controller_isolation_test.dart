import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';

import 'journey_controller_test.dart';
import 'journey_restart_test.dart';

void main() {
  _raceTests();
  test('ack generations are conditionally consumed', _ackGeneration);
  for (final first in const [false, true]) {
    test('${first ? 'resolved' : 'pending'} lens ack', () => _ackSelect(first));
  }
  _custodyTests();
  _modelContractTests();
}

void _raceTests() {
  for (final kind in const ['append', 'check', 'cancel']) {
    test('$kind pre-ack selection refreshes', () => _sameRace(kind, 'pre'));
    test('$kind exact-ack selection', () => _sameRace(kind, 'exact'));
    for (final result in const ['error', 'malformed']) {
      test('$kind $result ack response', () => _sameRace(kind, result));
    }
  }
  for (final kind in const ['append', 'check', 'cancel']) {
    test('$kind completed selection', () => _crossRace(kind, false));
    test('$kind pending selection', () => _crossRace(kind, true));
  }
  test('conflict ref/evidence isolation', () => _crossRace('conflict', false));
  test('cross-Journey ack truth', () => _crossRace('refreshing', false));
}

Future<void> _sameRace(String kind, String result) async {
  final (api, harness) = await ready();
  final item = draft(kind == 'cancel' ? 'append' : kind);
  if (kind != 'cancel') harness.controller.saveDraft(item);
  final outcome = Completer<Object>();
  final selection = Completer<JourneyProjection>();
  final operation = kind == 'check' ? operationA : null;
  api
    ..mutation(kind, outcome.future, operationRef: operation)
    ..reply(resumeDiag, selection.future);
  if (result == 'pre') {
    api.reply(resumeDiag, projection(head: headB, lens: diag));
  }
  final submitted = harness.submit(kind, item);
  await api.waitFor(kind);
  final selected = harness.controller.selectLens(diag);
  outcome.complete(kind == 'cancel'
      ? cancelResult()
      : acknowledgement(operationRef: operation));
  await submitted;
  switch (result) {
    case 'pre':
      selection.complete(projection(lens: diag));
    case 'exact':
      selection.complete(projection(head: headB, lens: diag));
    case 'malformed':
      selection.complete(JourneyProjection.fromJson(const {}));
    default:
      selection.completeError(Exception('transport unavailable'));
  }
  await selected;
  final s = harness.controller.state;
  expect({s.activeJourneyRef, s.projection?.journeyRef}, {journeyA});
  if (const {'error', 'malformed'}.contains(result)) {
    expect(s.phase, JourneyViewPhase.failed);
    expect(s.recoveryActions, {refresh});
  } else {
    expect([s.selectedLens, s.projection?.eventHeadSha256], [diag, headB]);
    expect(api.calls.where((c) => c.endsWith(':diagnose')).length,
        result == 'pre' ? 2 : 1);
  }
  if (kind != 'cancel') expect(harness.drafts.list(), isEmpty);
}

Future<void> _crossRace(String kind, bool pending) async {
  final (api, harness) = await ready();
  final refreshing = kind == 'refreshing';
  final action = kind == 'conflict' || refreshing ? 'append' : kind;
  final item = draft(action == 'cancel' ? 'append' : action);
  if (action != 'cancel') harness.controller.saveDraft(item);
  final outcome = Completer<Object>();
  final selection = Completer<JourneyProjection>();
  final oldRefresh = Completer<JourneyProjection>();
  final operation = action == 'check' ? operationA : null;
  api
    ..mutation(action, refreshing ? acknowledgement() : outcome.future,
        operationRef: operation)
    ..reply(
        resumeB, pending ? selection.future : projection(journeyRef: journeyB))
    ..reply(resumeA, refreshing ? oldRefresh.future : projection(head: headB));
  final submitted = harness.submit(action, item);
  await api.waitFor(refreshing ? resumeA : action);
  final selected = harness.controller.selectJourney(journeyB);
  if (!pending) await selected;
  if (refreshing) {
    oldRefresh.complete(projection(head: headB));
    await submitted;
    var state = harness.controller.state;
    expect({state.activeJourneyRef, state.projection?.journeyRef}, {journeyB});
    api
      ..reply(resumeA, projection())
      ..reply(resumeA, projection(head: headB));
    await harness.controller.selectJourney(journeyA);
    state = harness.controller.state;
    expect(state.projection?.eventHeadSha256, headB);
    return;
  }
  if (kind == 'conflict') {
    outcome.completeError(failure('HEAD_CONFLICT'));
  } else {
    outcome.complete(action == 'cancel'
        ? cancelResult()
        : acknowledgement(operationRef: operation));
  }
  await submitted;
  if (pending) {
    selection.complete(projection(journeyRef: journeyB));
    await selected;
  }
  final state = harness.controller.state;
  expect({state.activeJourneyRef, state.projection?.journeyRef}, {journeyB});
  if (action == 'cancel') {
    expect([state.activeOperationRef, state.cancelResult], [null, null]);
  }
}

Future<void> _ackGeneration() async {
  final (api, harness) = await ready();
  final first = harness.save(draft('append'));
  final second = harness
      .save(draft('append', ref: 'dft_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
  final ack1 = Completer<JourneyMutationAck>();
  final selection = Completer<JourneyProjection>();
  final oldRefresh = Completer<JourneyProjection>();
  api
    ..mutation('append', ack1.future)
    ..reply(resumeDiag, selection.future)
    ..reply(resumeDiag, oldRefresh.future)
    ..reply(resumeDiag, projection(head: headC, lens: diag));
  final one = harness.controller.submitAppend(first);
  await api.waitFor('append');
  final selected = harness.controller.selectLens(diag);
  ack1.complete(acknowledgement());
  await one;
  selection.complete(projection(lens: diag));
  while (api.calls.where((c) => c.endsWith(':diagnose')).length < 2) {
    await Future<void>.delayed(Duration.zero);
  }
  api.mutation('append', acknowledgement(head: headC));
  await harness.controller.submitAppend(second);
  oldRefresh.complete(projection(head: headB, lens: diag));
  await selected;
  expect(harness.controller.state.projection?.eventHeadSha256, headC);
  expect(harness.drafts.list(), isEmpty);
}

Future<void> _ackSelect(bool selectionFirst) async {
  final (api, harness) = await ready();
  final oldRefresh = Completer<JourneyProjection>();
  final selection = Completer<JourneyProjection>();
  final newRefresh = Completer<JourneyProjection>();
  api
    ..mutation('append', acknowledgement())
    ..reply(resumeA, oldRefresh.future)
    ..reply(resumeDiag, selection.future)
    ..reply(resumeDiag, newRefresh.future);
  final submitted =
      harness.controller.submitAppend(harness.save(draft('append')));
  await api.waitFor(resumeA);
  final selected = harness.controller.selectLens(diag);
  if (selectionFirst) {
    selection.complete(projection(lens: diag));
  } else {
    oldRefresh.complete(projection(head: headB));
    await submitted;
    selection.complete(projection(lens: diag));
  }
  while (api.calls.where((call) => call.endsWith(':diagnose')).length < 2) {
    await Future<void>.delayed(Duration.zero);
  }
  if (selectionFirst) oldRefresh.complete(projection(head: headB));
  await submitted;
  newRefresh.complete(projection(head: headB, lens: diag));
  await selected;
  final state = harness.controller.state;
  expect([state.selectedLens, state.projection?.lens], [diag, diag]);
  expect(state.projection?.eventHeadSha256, headB);
  expect(api.calls.where((call) => call.endsWith(':diagnose')), hasLength(2));
}

void _custodyTests() {
  for (final x in const [false, true]) {
    test('${x ? 'exact' : 'pre'} session failure', () => _sessionFail(x));
  }
  test('durable ack refreshes with edited draft', () async {
    final (api, harness) = await ready();
    final item = harness.save(draft('append'));
    final pending = Completer<JourneyMutationAck>();
    api
      ..mutation('append', pending.future)
      ..reply(resumeA, projection(head: headB));
    final submitted = harness.controller.submitAppend(item);
    await api.waitFor('append');
    harness.drafts.save(edited(item));
    pending.complete(acknowledgement());
    await submitted;
    expect(api.calls.last, resumeA);
    expect(harness.controller.state.projection?.eventHeadSha256, headB);
    expect(harness.drafts.list(), hasLength(1));
    expect(harness.controller.state.recoveryActions, ackRecovery);
  });

  test('create ack survives session write failure', () async {
    final api = ScriptedJourneyApi();
    final harness =
        ControllerHarness(api, sessionBeforeRename: (_) => failWrite());
    addTearDown(harness.dispose);
    final item = harness.save(draft('create'));
    api
      ..mutation('create', acknowledgement())
      ..reply(resumeA, projection(head: headB));
    await harness.controller.submitStart(item);
    final state = harness.controller.state;
    expect(api.calls.last, resumeA);
    expect(state.activeJourneyRef, journeyA);
    expect(state.projection?.eventHeadSha256, headB);
    expect(state.localFailure, writeFailed);
    expect(state.recoveryActions, ackRecovery);
  });
}

Future<void> _sessionFail(bool exact) async {
  var failWrites = false;
  final api = ScriptedJourneyApi();
  final harness = await readyHarness(api, rename: (_) {
    if (failWrites) failWrite();
  });
  failWrites = true;
  final mutation = Completer<JourneyMutationAck>();
  final selection = Completer<JourneyProjection>();
  api
    ..mutation('append', mutation.future)
    ..reply(resumeDiag, selection.future);
  final submitted =
      harness.controller.submitAppend(harness.save(draft('append')));
  await api.waitFor('append');
  final selected = harness.controller.selectLens(diag);
  mutation.complete(acknowledgement());
  await submitted;
  selection.complete(projection(head: exact ? headB : headA, lens: diag));
  await selected;
  final state = harness.controller.state;
  expect(state.localFailure, writeFailed);
  expect(state.remoteFailure, isNull);
  expect(state.recoveryActions, ackRecovery);
  expect(harness.drafts.list(), isEmpty);
}

void _modelContractTests() {
  test('check wrapper and view collections fail closed and immutable', () {
    final valid = draft('check');
    expect(JourneyCheckDraft.fromDraft(valid).clientRequestId, 'request-check');
    expect(
      () => JourneyCheckDraft.fromDraft(
          draft('check', payload: {...valid.payload, 'extra': 'value'})),
      throwsA(isA<JourneyLocalStoreException>()),
    );
    final harness = ControllerHarness(ScriptedJourneyApi());
    addTearDown(harness.dispose);
    final state = harness.controller.state;
    expect(() => state.drafts.add(valid), throwsUnsupportedError);
    expect(() => state.recoveryActions.add(review), throwsUnsupportedError);
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

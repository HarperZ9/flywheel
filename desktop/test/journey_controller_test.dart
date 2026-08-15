import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';

const journeyA = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const journeyB = 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const operationA = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const proposalA = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const grantA = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
JourneyProjection projection({
  String journeyRef = journeyA,
  String head = headA,
  JourneyLens lens = JourneyLens.verify,
  String fact = 'fact-1',
}) =>
    JourneyProjection.fromJson({
      'schema': 'flywheel.evidence-journey-projection/v2',
      'journey_ref': journeyRef,
      'event_head_sha256': head,
      'fact_ids': [fact],
      'claim_ids': const ['claim-1'],
      'checks': const [],
      'verdicts': const {'claim-1': 'UNDECIDED'},
      'missing_evidence': const [],
      'stage': 'running',
      'conclusion': null,
      'next_actions': const [],
      'detail': 'Accepted server detail',
      'lens': switch (lens) {
        JourneyLens.rescue => 'Rescue',
        JourneyLens.diagnose => 'Diagnose',
        _ => 'Verify',
      },
    });
GrantProposal proposal(String action, {String? operationRef}) =>
    GrantProposal.fromJson({
      'schema': 'flywheel.grant-proposal/v1',
      'proposal_ref': proposalA,
      'planned_grant_ref': grantA,
      'action': action,
      'operation_sha256': headA,
      'expires_at': '2026-08-15T12:00:00Z',
      if (operationRef != null) 'operation_ref': operationRef,
    });
GrantRef approval({String grantRef = grantA}) => GrantRef.fromJson({
      'schema': 'flywheel.operation-grant-approval/v1',
      'grant_ref': grantRef,
      'expires_at': '2026-08-15T12:00:00Z',
    });
JourneyMutationAck acknowledgement({
  String journeyRef = journeyA,
  String head = headB,
  String? operationRef,
  String? operationState,
  bool includeOperationState = true,
}) =>
    JourneyMutationAck.fromJson({
      'schema': 'flywheel.evidence-journey-mutation-ack/v2',
      'journey_ref': journeyRef,
      'event_head_sha256': head,
      'event_sha256': headB,
      'projection_sha256': headA,
      'idempotent_replay': false,
      if (operationRef != null) 'operation_ref': operationRef,
      if (includeOperationState && operationRef != null)
        'state': operationState ?? 'completed'
      else if (operationState != null)
        'state': operationState,
    });
JourneyDraft draft(String kind,
    {String ref = 'dft_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    String? journeyRef = journeyA,
    String? baseHead}) {
  final payload = switch (kind) {
    'create' => <Object?, Object?>{
        'client_request_id': 'request-create',
        'goal': 'Preserve evidence',
        'intake_ref': 'intake.json',
      },
    'append' => <Object?, Object?>{
        'client_request_id': 'request-append',
        'command': {'kind': 'record_fact', 'fact_ref': 'fact.json'},
      },
    _ => <Object?, Object?>{
        'client_request_id': 'request-check',
        'claim_id': 'claim-1',
        'oracle_id': 'code',
        'candidate_ref': 'candidate.py',
        'context_ref': 'context.json',
      },
  };
  return JourneyDraft(
    draftRef: ref,
    journeyRef: kind == 'create' ? null : journeyRef,
    baseEventHeadSha256: baseHead,
    kind: kind,
    payload: payload,
    state: JourneyDraftState.dirty,
    updatedAt: DateTime.utc(2026, 8, 15),
  );
}

class ScriptedJourneyApi implements JourneyApi {
  final Map<String, List<Object>> replies = {};
  final List<String> calls = [];
  final List<JourneyAppendRequest> appendRequests = [];
  final List<JourneyCheckRequest> checkRequests = [];
  final List<JourneyCreateRequest> createRequests = [];
  final List<JourneyCancelRequest> cancelRequests = [];
  void reply(String name, Object value) =>
      replies.putIfAbsent(name, () => []).add(value);
  Future<T> _take<T>(String name) async {
    calls.add(name);
    final value = replies[name]!.removeAt(0);
    if (value is Future) return (await value) as T;
    if (value is Exception || value is Error) throw value;
    return value as T;
  }

  @override
  Future<GrantProposal> prepareGrant(GrantIntent intent) => _take('prepare');
  @override
  Future<GrantRef> approveGrantOnce(String proposalRef) => _take('approve');
  @override
  Future<JourneyMutationAck> create(JourneyCreateRequest request) {
    createRequests.add(request);
    return _take('create');
  }

  @override
  Future<List<JourneySummary>> list() => _take('list');
  @override
  Future<JourneyProjection> resume(String ref, JourneyLens lens) =>
      _take('resume:$ref:${lens.name}');
  @override
  Future<JourneyMutationAck> append(JourneyAppendRequest request) {
    appendRequests.add(request);
    return _take('append');
  }

  @override
  Future<JourneyMutationAck> check(JourneyCheckRequest request) {
    checkRequests.add(request);
    return _take('check');
  }

  @override
  Future<JourneyCancelResult> cancel(JourneyCancelRequest request) {
    cancelRequests.add(request);
    return _take('cancel');
  }

  @override
  Future<JourneyExportResult> export(JourneyExportRequest request) =>
      throw UnimplementedError();
}

class ControllerHarness {
  ControllerHarness(this.api, {JourneyBeforeRename? sessionBeforeRename})
      : directory = Directory.systemTemp.createTempSync('journey-controller-') {
    drafts = JourneyDraftStore(file: File('${directory.path}/drafts.json'));
    sessions = JourneySessionStore(
        file: File('${directory.path}/session.json'),
        beforeRename: sessionBeforeRename);
    controller = JourneyController(
      api: api,
      draftStore: drafts,
      sessionStore: sessions,
    );
  }
  final ScriptedJourneyApi api;
  final Directory directory;
  late final JourneyDraftStore drafts;
  late final JourneySessionStore sessions;
  late final JourneyController controller;
  void dispose() => directory.deleteSync(recursive: true);
}

Future<ControllerHarness> readyHarness(ScriptedJourneyApi api) async {
  final harness = ControllerHarness(api);
  harness.sessions
      .save(JourneySession(journeyRef: journeyA, lens: JourneyLens.verify));
  api.reply('resume:$journeyA:verify', projection());
  api.reply('list', <JourneySummary>[projection()]);
  await harness.controller.initialize();
  api.calls.clear();
  return harness;
}

void main() {
  _contractTests();
  _mutationTests();
}

void _contractTests() {
  test('append preserves request and deletes only on ack', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final item = draft('append');
    harness.controller.saveDraft(item);
    api
      ..reply('prepare', proposal('append'))
      ..reply('approve', approval())
      ..reply('append', acknowledgement())
      ..reply('resume:$journeyA:verify', projection(head: headB));
    await harness.controller.submitAppend(item);
    expect(
        api.calls, ['prepare', 'approve', 'append', 'resume:$journeyA:verify']);
    final request = api.appendRequests.single;
    expect(request.clientRequestId, 'request-append');
    expect(request.expectedEventHead, headA);
    expect(request.command, item.payload['command']);
    expect(harness.drafts.list(), isEmpty);
    expect(harness.controller.state.projection?.eventHeadSha256, headB);
  });
}

void _mutationTests() {
  test('check binds exact fields and operation refs', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final item = draft('check');
    harness.controller.saveDraft(item);
    api
      ..reply('prepare', proposal('check', operationRef: operationA))
      ..reply('approve', approval())
      ..reply('check', acknowledgement(operationRef: operationA))
      ..reply('resume:$journeyA:verify', projection(head: headB));
    await harness.controller.runCheck(JourneyCheckDraft.fromDraft(item));
    final request = api.checkRequests.single;
    expect([request.clientRequestId, request.claimId, request.oracleId],
        ['request-check', 'claim-1', 'code']);
    expect([request.candidateRef, request.contextRef],
        ['candidate.py', 'context.json']);
    expect(harness.controller.state.activeOperationRef, operationA);
    expect(harness.drafts.list(), isEmpty);
  });
  test('mutations are FIFO and typed failures preserve projection', () async {
    final api = ScriptedJourneyApi();
    final harness = await readyHarness(api);
    addTearDown(harness.dispose);
    final blocked = Completer<GrantProposal>();
    final first = draft('append');
    final second = draft('append', ref: 'dft_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
    harness.controller
      ..saveDraft(first)
      ..saveDraft(second);
    api
      ..reply('prepare', blocked.future)
      ..reply('approve', approval())
      ..reply('append', acknowledgement())
      ..reply('resume:$journeyA:verify', projection(head: headB))
      ..reply(
          'prepare',
          JourneyApiException(JourneyFailure(
              'AUTH_REQUIRED', 'Journey authorization is required', const [])));
    final one = harness.controller.submitAppend(first);
    final two = harness.controller.submitAppend(second);
    await Future<void>.delayed(Duration.zero);
    expect(api.calls, ['prepare']);
    blocked.complete(proposal('append'));
    await one;
    await two;
    expect(api.calls.where((call) => call == 'prepare').length, 2);
    expect(harness.controller.state.phase, JourneyViewPhase.blocked);
    expect(harness.controller.state.recoveryActions, {
      JourneyRecoveryAction.authenticate,
      JourneyRecoveryAction.retrySameRequest
    });
    expect(harness.controller.state.projection?.eventHeadSha256, headB);
  });
}

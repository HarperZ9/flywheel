import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';

const journeyA = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const headC =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
const operationA = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const proposalA = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const grantA = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const resumeA = 'resume:$journeyA:verify';
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
        'state': operationState ?? 'completed',
      if (operationRef == null && operationState != null)
        'state': operationState,
    });
JourneyApiException failure(String code) =>
    JourneyApiException(JourneyFailure(code, 'Fixed failure detail', const []));
JourneyDraft draft(String kind,
    {String ref = 'dft_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    String? journeyRef = journeyA,
    String? baseHead,
    Map<Object?, Object?>? payload}) {
  final value = payload ??
      switch (kind) {
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
    payload: value,
    state: JourneyDraftState.dirty,
    updatedAt: DateTime.utc(2026, 8, 15),
  );
}

JourneyDraft edited(JourneyDraft item) =>
    draft('append', ref: item.draftRef, baseHead: headA, payload: {
      ...item.payload,
      'command': {'kind': 'changed'}
    });

class ScriptedJourneyApi implements JourneyApi {
  final Map<String, List<Object>> replies = {};
  final List<String> calls = [];
  final List<JourneyAppendRequest> appendRequests = [];
  final List<JourneyCheckRequest> checkRequests = [];
  final List<JourneyCreateRequest> createRequests = [];
  final List<JourneyCancelRequest> cancelRequests = [];
  void reply(String name, Object value) =>
      replies.putIfAbsent(name, () => []).add(value);
  void mutation(String action, Object result, {String? operationRef}) {
    reply('prepare', proposal(action, operationRef: operationRef));
    reply('approve', approval());
    reply(action, result);
  }

  Future<void> waitFor(String call) async {
    while (!calls.contains(call)) {
      await Future<void>.delayed(Duration.zero);
    }
  }

  Future<T> _take<T>(String name) async {
    calls.add(name);
    final value = replies[name]!.removeAt(0);
    if (value is Future) return (await value) as T;
    if (value is Exception || value is Error) throw value;
    return value as T;
  }

  Future<T> _record<T, R>(String name, List<R> records, R request) {
    records.add(request);
    return _take(name);
  }

  @override
  Future<GrantProposal> prepareGrant(GrantIntent intent) => _take('prepare');
  @override
  Future<GrantRef> approveGrantOnce(String proposalRef) => _take('approve');
  @override
  Future<JourneyMutationAck> create(JourneyCreateRequest request) =>
      _record('create', createRequests, request);
  @override
  Future<List<JourneySummary>> list() => _take('list');
  @override
  Future<JourneyProjection> resume(String ref, JourneyLens lens) =>
      _take('resume:$ref:${lens.name}');
  @override
  Future<JourneyMutationAck> append(JourneyAppendRequest request) =>
      _record('append', appendRequests, request);
  @override
  Future<JourneyMutationAck> check(JourneyCheckRequest request) =>
      _record('check', checkRequests, request);
  @override
  Future<JourneyCancelResult> cancel(JourneyCancelRequest request) =>
      _record('cancel', cancelRequests, request);
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
  JourneyDraft save(JourneyDraft item) {
    controller.saveDraft(item);
    return item;
  }

  Future<void> submit(String kind, JourneyDraft item) => switch (kind) {
        'check' => controller.runCheck(JourneyCheckDraft.fromDraft(item)),
        'cancel' => controller.requestCancel(operationA),
        _ => controller.submitAppend(item),
      };
  void dispose() => directory.deleteSync(recursive: true);
}

Future<ControllerHarness> readyHarness(ScriptedJourneyApi api,
    {JourneyBeforeRename? rename}) async {
  final harness = ControllerHarness(api, sessionBeforeRename: rename);
  addTearDown(harness.dispose);
  harness.sessions
      .save(JourneySession(journeyRef: journeyA, lens: JourneyLens.verify));
  api.reply(resumeA, projection());
  api.reply('list', <JourneySummary>[projection()]);
  await harness.controller.initialize();
  api.calls.clear();
  return harness;
}

Future<(ScriptedJourneyApi, ControllerHarness)> ready() async {
  final api = ScriptedJourneyApi();
  return (api, await readyHarness(api));
}

void main() {
  _contractTests();
  _mutationTests();
}

void _contractTests() {
  test('append preserves request and deletes only on ack', () async {
    final (api, harness) = await ready();
    final item = harness.save(draft('append'));
    api
      ..mutation('append', acknowledgement())
      ..reply(resumeA, projection(head: headB));
    await harness.controller.submitAppend(item);
    expect(api.calls, ['prepare', 'approve', 'append', resumeA]);
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
    final (api, harness) = await ready();
    final item = harness.save(draft('check'));
    api
      ..mutation('check', acknowledgement(operationRef: operationA),
          operationRef: operationA)
      ..reply(resumeA, projection(head: headB));
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
    final (api, harness) = await ready();
    final blocked = Completer<GrantProposal>();
    final first = harness.save(draft('append'));
    final second = harness
        .save(draft('append', ref: 'dft_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    api
      ..reply('prepare', blocked.future)
      ..reply('approve', approval())
      ..reply('append', acknowledgement())
      ..reply(resumeA, projection(head: headB))
      ..reply('prepare', failure('AUTH_REQUIRED'));
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

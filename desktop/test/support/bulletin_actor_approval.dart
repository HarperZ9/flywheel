import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/models/approval_review_models.dart';
import 'bulletin_actor_exchange.dart';

Future<void> announceActorReady(
    GatewayGrantClient client, ActorExchange exchange) async {
  if (!(await client.capabilities()).ready) actorInvalid();
  exchange.writeReady();
}

/// Synthetic-only driver. It approves exactly the retained operation through
/// production APIs; the supervisor's decision and reservation arrive by IPC.
class ActorApprovalDriver {
  ActorApprovalDriver(this.client, this.records,
      {required this.runId,
      required this.slotId,
      required this.proposalSha,
      required this.reviewWait,
      this.recordingFailed,
      this.activeBudget = const Duration(seconds: 240)});
  final GatewayGrantClient client;
  final ActorRecords records;
  final String runId, slotId, proposalSha;
  final Duration reviewWait;
  final Duration activeBudget;
  final bool Function()? recordingFailed;
  final _active = Stopwatch();
  void _checkActive() {
    if (_active.elapsed >= activeBudget) actorInvalid();
  }

  bool _started = false;
  String stage = 'capabilities';
  String? reservationId;
  bool requestEntered = false, responseReceived = false;
  Map<String, Object?> get _base => {
        'schema_version': 1,
        'run_id': runId,
        'slot_id': slotId,
        'proposal_sha256': proposalSha
      };

  Future<void> ready() async {
    if (!(await client.capabilities()).ready) actorInvalid();
  }

  Future<void> run(GatewayOperation operation, GatewayJourneyBinding binding,
      {bool capabilityChecked = false}) async {
    if (_started) actorInvalid();
    _started = true;
    _active.start();
    var disposition = 'incomplete';
    String? postId, errorCode;
    try {
      if (!capabilityChecked) await ready();
      _checkActive();
      stage = 'prepare';
      final proposed = await client.prepare(operation, binding: binding);
      _checkActive();
      stage = 'read';
      final read = await client.readProposal(proposed.proposalRef);
      _checkActive();
      stage = 'review_validate';
      final review = read.review;
      if (!read.approvable ||
          review == null ||
          read.recordSha256Field != review.recordSha256 ||
          review.proposalRef != proposed.proposalRef ||
          review.plannedGrantRef != proposed.plannedGrantRef ||
          review.operationSha256 != proposed.operationSha256 ||
          review.argumentsSha256 != proposed.argumentsSha256) {
        actorInvalid();
      }
      stage = 'review_binding';
      _matchReview(review, operation, binding);
      stage = 'review_record';
      records.write(
          'review.json', {..._base, 'review': review.toExactJson()}, 65536);
      stage = 'decision';
      _active.stop();
      final reviewClock = Stopwatch()..start();
      final decision = await records.wait('decision.json', 8192, reviewWait);
      _decision(decision.value, review);
      if (decision.value['decision'] == 'reject') {
        _active.start();
        _checkActive();
        stage = 'reject';
        await client.rejectProposal(review.proposalRef, review.recordSha256);
        disposition = 'rejected';
      } else {
        stage = 'reservation';
        final remaining = reviewWait - reviewClock.elapsed;
        if (remaining <= Duration.zero) actorInvalid();
        final permit =
            await records.wait('dispatch-permit.json', 8192, remaining);
        _active.start();
        _checkActive();
        _permit(permit.value, decision.sha256, review);
        reservationId = permit.value['reservation_id'] as String;
        stage = 'approve';
        final approval = await client.approveReviewed(
            review.proposalRef, review.reviewSha256);
        _checkActive();
        if (approval.grantRef != review.plannedGrantRef ||
            !_future(approval.expiresAt)) {
          actorInvalid();
        }
        stage = 'dispatch';
        _checkActive();
        requestEntered = true; // Invocation intent, not proof of HTTP delivery.
        final result = await client.dispatch(operation,
            path: '/api/lane/bulletin/board_write_post',
            binding: binding,
            grantRef: approval.grantRef);
        responseReceived = true;
        if (actorId(result['post_id'])) postId = result['post_id'] as String;
        disposition = 'response_received';
      }
    } on Object {
      errorCode = recordingFailed?.call() == true
          ? 'native_recording_failed'
          : 'native_driver_incomplete';
    }
    records.write(
        'result.json',
        {
          ..._base,
          'reservation_id': reservationId,
          'stage': stage,
          'disposition': disposition,
          'request_entered': requestEntered,
          'response_received': responseReceived,
          'post_id': postId,
          'error_code': errorCode
        },
        16384);
  }

  bool _future(String value) {
    if (!RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$')
        .hasMatch(value)) {
      return false;
    }
    final expiry = DateTime.tryParse(value);
    return expiry != null &&
        expiry.isUtc &&
        expiry.toIso8601String().substring(0, 19) == value.substring(0, 19) &&
        expiry.isAfter(DateTime.now().toUtc());
  }

  void _matchReview(
      GatewayGrantReview r, GatewayOperation op, GatewayJourneyBinding b) {
    if (r.action != op.action ||
        r.journeyRef != b.journeyRef ||
        r.eventHead != b.eventHead ||
        r.clientRequestId != op.clientRequestId ||
        r.destination != op.destination ||
        r.tool != op.tool ||
        !sameGatewayValue(r.operation, op.operation) ||
        !sameGatewayStringList(r.scopes, op.scopes) ||
        !sameGatewayStringList(r.dataRefs, op.dataRefs) ||
        !sameGatewayStringList(r.credentialRefs, op.credentialRefs) ||
        !_future(r.expiresAt)) {
      actorInvalid();
    }
  }

  void _correlate(Map<String, Object?> value) {
    if (value['run_id'] != runId || value['slot_id'] != slotId) actorInvalid();
  }

  void _decision(Map<String, Object?> v, GatewayGrantReview r) {
    actorFields(v, {
      'schema_version',
      'run_id',
      'slot_id',
      'proposal_sha256',
      'review_sha256',
      'operation_sha256',
      'proposal_ref',
      'reviewer_id',
      'reviewer_type',
      'decision',
      'duration_ms'
    });
    _correlate(v);
    if (v['proposal_sha256'] != proposalSha ||
        v['review_sha256'] != r.reviewSha256 ||
        v['operation_sha256'] != r.operationSha256 ||
        v['proposal_ref'] != r.proposalRef ||
        !actorId(v['reviewer_id']) ||
        !{'human', 'assistant_supervisor'}.contains(v['reviewer_type']) ||
        !{'approve', 'reject'}.contains(v['decision']) ||
        v['duration_ms'] is! int ||
        (v['duration_ms'] as int) < 0 ||
        (v['duration_ms'] as int) > reviewWait.inMilliseconds) {
      actorInvalid();
    }
  }

  void _permit(
      Map<String, Object?> v, String decisionSha, GatewayGrantReview r) {
    actorFields(v, {
      'schema_version',
      'run_id',
      'slot_id',
      'reservation_id',
      'decision_sha256',
      'review_sha256',
      'operation_sha256'
    });
    _correlate(v);
    if (!actorId(v['reservation_id']) ||
        v['decision_sha256'] != decisionSha ||
        v['review_sha256'] != r.reviewSha256 ||
        v['operation_sha256'] != r.operationSha256 ||
        !_future(r.expiresAt)) {
      actorInvalid();
    }
  }
}

import '../models/writing_models.dart';
import 'gateway_client.dart';

abstract interface class WritingApi {
  Future<Map<String, dynamic>> doctor();
  Future<WritingStatus> status();
  Future<WritingProjectView> project(String journeyRef);
  Future<WritingProposal> prepareInit({
    required Map<String, dynamic> brief,
    required Map<String, dynamic> sourcePacket,
    required String clientRequestId,
  });
  Future<WritingProposal> prepareSection({
    required String journeyRef,
    required String expectedEventHead,
    required Map<String, dynamic> section,
    required String clientRequestId,
  });
  Future<WritingProposal> prepareRevision({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String sectionRef,
    required String body,
    required String clientRequestId,
  });
  Future<WritingProposal> prepareDiagnose({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String revisionRef,
    required String clientRequestId,
  });
  Future<WritingProposal> prepareCard({
    required String journeyRef,
    required String expectedEventHead,
    required Map<String, dynamic> card,
    required String clientRequestId,
  });
  Future<WritingProposal> prepareCandidate({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String cardRef,
    required String body,
    required String clientRequestId,
  });
  Future<WritingProposal> prepareDecision({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String decision,
    String? candidateRef,
    String? sectionRef,
    String? toRevisionRef,
    String? reason,
    required String clientRequestId,
  });
  Future<WritingProposal> prepareExport({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String outRef,
    required String clientRequestId,
  });
  Future<WritingProposalPreview> proposalGet(String proposalRef);
  Future<Map<String, dynamic>> approve(String proposalRef);
  Future<Map<String, dynamic>> commit(String proposalRef, String grantRef);
}

final class GatewayWritingApi implements WritingApi {
  final GatewayClient _client;
  GatewayWritingApi(this._client);

  @override
  Future<Map<String, dynamic>> doctor() => _client.getJson('/api/writing/doctor');

  @override
  Future<WritingStatus> status() async =>
      WritingStatus.fromJson(await _client.getJson('/api/writing/status'));

  @override
  Future<WritingProjectView> project(String journeyRef) async {
    final query = Uri.encodeQueryComponent(journeyRef);
    return WritingProjectView.fromJson(
        await _client.getJson('/api/writing/project?journey_ref=$query'));
  }

  @override
  Future<WritingProposal> prepareInit({
    required Map<String, dynamic> brief,
    required Map<String, dynamic> sourcePacket,
    required String clientRequestId,
  }) => _proposal('/api/writing/init/prepare', {
        'brief': brief,
        'source_packet': sourcePacket,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposal> prepareSection({
    required String journeyRef,
    required String expectedEventHead,
    required Map<String, dynamic> section,
    required String clientRequestId,
  }) => _proposal('/api/writing/section/prepare', {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'section': section,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposal> prepareRevision({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String sectionRef,
    required String body,
    required String clientRequestId,
  }) => _proposal('/api/writing/revision/prepare', {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'project_ref': projectRef,
        'section_ref': sectionRef,
        'body': body,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposal> prepareDiagnose({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String revisionRef,
    required String clientRequestId,
  }) => _proposal('/api/writing/diagnose/prepare', {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'project_ref': projectRef,
        'revision_ref': revisionRef,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposal> prepareCard({
    required String journeyRef,
    required String expectedEventHead,
    required Map<String, dynamic> card,
    required String clientRequestId,
  }) => _proposal('/api/writing/card/prepare', {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'card': card,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposal> prepareCandidate({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String cardRef,
    required String body,
    required String clientRequestId,
  }) => _proposal('/api/writing/candidate/prepare', {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'project_ref': projectRef,
        'card_ref': cardRef,
        'body': body,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposal> prepareDecision({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String decision,
    String? candidateRef,
    String? sectionRef,
    String? toRevisionRef,
    String? reason,
    required String clientRequestId,
  }) => _proposal('/api/writing/decision/prepare', {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'project_ref': projectRef,
        'decision': decision,
        if (candidateRef != null) 'candidate_ref': candidateRef,
        if (sectionRef != null) 'section_ref': sectionRef,
        if (toRevisionRef != null) 'to_revision_ref': toRevisionRef,
        if (reason != null) 'reason': reason,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposal> prepareExport({
    required String journeyRef,
    required String expectedEventHead,
    required String projectRef,
    required String outRef,
    required String clientRequestId,
  }) => _proposal('/api/writing/export/prepare', {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'project_ref': projectRef,
        'out_ref': outRef,
        'client_request_id': clientRequestId,
      });

  @override
  Future<WritingProposalPreview> proposalGet(String proposalRef) async =>
      WritingProposalPreview.fromJson(await _client.postJson(
          '/api/writing/proposal/get', {'proposal_ref': proposalRef}));

  @override
  Future<Map<String, dynamic>> approve(String proposalRef) => _client.postJson(
      '/api/writing/proposal/approve', {'proposal_ref': proposalRef});

  @override
  Future<Map<String, dynamic>> commit(String proposalRef, String grantRef) =>
      _client.postJson('/api/writing/proposal/commit', {
        'proposal_ref': proposalRef,
        'grant_ref': grantRef,
      });

  Future<WritingProposal> _proposal(
          String path, Map<String, dynamic> body) async =>
      WritingProposal.fromJson(await _client.postJson(path, body));
}

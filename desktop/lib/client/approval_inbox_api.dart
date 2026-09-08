import '../models/approval_inbox_models.dart';
import 'gateway_client.dart';
import 'gateway_grants.dart';

abstract interface class ApprovalInboxApi {
  Future<GatewayGrantCapabilities> fetchCapabilities();
  Future<GatewayGrantList> listPending({int limit = 25, String? cursor});
  Future<GatewayGrantRead> readProposal(String proposalRef);
  Future<GatewayGrantApproval> approveReviewed(
      String proposalRef, String reviewSha256);
  Future<GatewayGrantRejection> rejectProposal(
      String proposalRef, String recordSha256);
  Future<ActiveWorkSnapshot> activeWorkSnapshot();
}

final class GatewayApprovalInboxApi implements ApprovalInboxApi {
  final GatewayGrantClient _grants;
  final GatewayClient _client;

  GatewayApprovalInboxApi(GatewayClient client)
      : _client = client,
        _grants = GatewayGrantClient(client);

  @override
  Future<GatewayGrantCapabilities> fetchCapabilities() =>
      _grants.capabilities();

  @override
  Future<GatewayGrantList> listPending({int limit = 25, String? cursor}) =>
      _grants.listPending(limit: limit, cursor: cursor);

  @override
  Future<GatewayGrantRead> readProposal(String proposalRef) =>
      _grants.readProposal(proposalRef);

  @override
  Future<GatewayGrantApproval> approveReviewed(
          String proposalRef, String reviewSha256) =>
      _grants.approveReviewed(proposalRef, reviewSha256);

  @override
  Future<GatewayGrantRejection> rejectProposal(
          String proposalRef, String recordSha256) =>
      _grants.rejectProposal(proposalRef, recordSha256);

  @override
  Future<ActiveWorkSnapshot> activeWorkSnapshot() async {
    try {
      final doc = await _client.relayRuns();
      final raw = doc['runs'];
      if (raw is! List) {
        return const ActiveWorkSnapshot.unavailable(
            'Active work status unavailable');
      }
      return ActiveWorkSnapshot(
          items: List.unmodifiable([
        for (final run in raw)
          if (ActiveWorkItem.fromRelay(run) case final item?) item
      ]));
    } on Object {
      return const ActiveWorkSnapshot.unavailable(
          'Active work status unavailable');
    }
  }
}

part of 'gateway_client.dart';

extension GatewayProviderSessionBindings on GatewayClient {
  Future<ProviderSessionBinding> providerSessionBinding(
          ProviderSessionBindingRequest request) async =>
      ProviderSessionBinding.fromJson(
        await postJson(providerSessionBindingPath, request.toJson()),
      );

  Future<ProviderSessionApprovals> providerSessionApprovals(
      String operationRef) async {
    if (!RegExp(r'^op_[0-9a-f]{32}$').hasMatch(operationRef)) {
      throw ArgumentError('Invalid operation reference');
    }
    final path =
        '$providerSessionApprovalsPath?operation_ref=${Uri.encodeQueryComponent(operationRef)}';
    return ProviderSessionApprovals.fromJson(await getJson(path));
  }

  Future<Map<String, dynamic>> respondProviderSessionApproval(
          Map<String, dynamic> finalBody) =>
      postJson(providerSessionApprovalsRespondPath, finalBody);
}

// gateway_infra.dart -- the infrastructure control routes.
//
// Three reads over the boundary the agent runs inside: the trust model and
// the components that would take the whole thing down alone, the run bill of
// materials, and the live egress table classified against the allowlist. The
// three acting routes are not here. A scan that reads where credentials live,
// a probe that leaves the machine, and the kill switch each go through the
// grant sheet, so their calls sit in the panels that ask for them.

import 'gateway_client.dart';

extension GatewayInfra on GatewayClient {
  Future<Map<String, dynamic>> infraTrustModel() =>
      getJson('/api/infra/trust-model');

  Future<Map<String, dynamic>> infraBom() => getJson('/api/infra/bom');

  Future<Map<String, dynamic>> infraEgress() => getJson('/api/infra/egress');
}

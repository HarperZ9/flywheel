// gateway_registry.dart - the engine's own registries and its stated belief.
//
// Read-only surfaces that existed on the gateway with nothing in the app
// calling them. Each returns a schema-tagged document; none of them mutate.

import 'gateway_client.dart';

extension GatewayRegistry on GatewayClient {
  /// GET /api/credo - the belief, content-addressed so it can be quoted and
  /// checked rather than paraphrased.
  Future<Map<String, dynamic>> credo() => getJson('/api/credo');

  /// GET /api/loops - which candidate loops close, measured rather than drawn.
  Future<Map<String, dynamic>> loops() => getJson('/api/loops');

  /// GET /api/hooks - the hook registry.
  Future<Map<String, dynamic>> hooks() => getJson('/api/hooks');

  /// GET /api/skills - the skill list.
  Future<Map<String, dynamic>> skills() => getJson('/api/skills');

  /// GET /api/packs - admitted domain packs.
  Future<Map<String, dynamic>> packs() => getJson('/api/packs');

  /// GET /api/credential-handles - handle presence only. The engine never
  /// returns a credential value and this never asks for one.
  Future<Map<String, dynamic>> credentialHandles() =>
      getJson('/api/credential-handles');
}

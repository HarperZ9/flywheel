// Library-private helpers for GatewayOperation: the bulletin board write
// binding and the two lane setting grants. Split from
// gateway_operation_internals.dart to hold that file under the size gate.

part of 'gateway_grant_models.dart';

/// The two lane setup choices (harness/lane_settings_route.py). Each has a
/// fixed destination and fixed scopes; the engine's proposal must match.
const _settingDestinations = {
  'settings.node_path': GatewayDestination('setting', 'node_path'),
  'lane.root': GatewayDestination('setting', 'local-model-root'),
};

List<String>? _settingScopes(String action, Map<String, Object?> value) {
  final fixed = switch (action) {
    'settings.node_path' => const ['write', 'exec'],
    'lane.root' => const ['write'],
    _ => null,
  };
  if (fixed == null) return null;
  final keyed = (value['credential_refs'] as List).isNotEmpty;
  return [...fixed, if (keyed) 'secrets'];
}

bool _isBulletinBoardWrite(String action, Map<String, Object?> value) =>
    action == 'lane.call' &&
    value['name'] == 'bulletin' &&
    value['tool'] == 'board_write_post';

void _validateBulletinOriginBinding(
  String action,
  Map<String, Object?> value,
  GatewayDestination destination,
) {
  final hasOrigin = value.containsKey('bulletin_base_url');
  if (!_isBulletinBoardWrite(action, value)) {
    if (hasOrigin || destination.bulletinBaseUrl != null) _invalid();
    return;
  }
  if (_containsBulletinOriginField(value['args'])) _invalid();
  final origin = value['bulletin_base_url'];
  if (origin is! String || !isCanonicalBulletinOrigin(origin)) _invalid();
  if (destination.kind != 'lane' ||
      destination.ref != 'bulletin' ||
      destination.bulletinBaseUrl != origin) {
    _invalid();
  }
}

bool _containsBulletinOriginField(Object? value) {
  if (value is Map) {
    for (final entry in value.entries) {
      if (entry.key == 'bulletin_base_url' ||
          _containsBulletinOriginField(entry.value)) {
        return true;
      }
    }
  }
  if (value is List) {
    return value.any(_containsBulletinOriginField);
  }
  return false;
}

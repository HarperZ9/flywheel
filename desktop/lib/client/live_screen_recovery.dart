import 'gateway_client.dart';

final _screenRecoveryId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,127}$');

/// Reads an owner-scoped lookup and accepts only the exact requested binding.
/// An empty result is inconclusive: the original open may still be in flight.
Future<Map<String, dynamic>?> recoverLiveScreenSession(
    GatewayClient client, Map<String, dynamic> requested) async {
  final ref = requested['body_session_ref'];
  if (ref is! String || !_screenRecoveryId.hasMatch(ref)) {
    throw const FormatException('Invalid screen recovery reference');
  }
  final data = await client.getJson('/api/live-screen/sessions?'
      'body_session_ref=${Uri.encodeQueryComponent(ref)}');
  return parseRecoveredScreenSession(data, requested);
}

Map<String, dynamic>? parseRecoveredScreenSession(
    Map<String, dynamic> data, Map<String, dynamic> requested) {
  final rows = data['sessions'];
  if (data['schema'] != 'flywheel.live-screen-session-list/v1' ||
      rows is! List ||
      data['count'] != rows.length ||
      rows.length > 1) {
    throw const FormatException('Ambiguous screen recovery response');
  }
  if (rows.isEmpty) return null;
  final row = rows.single;
  if (row is! Map<String, dynamic>) {
    throw const FormatException('Invalid screen recovery response');
  }
  final id = row['session_id'], binding = row['body_binding'];
  final sources = row['source_ids'], wanted = requested['sources'];
  if (id is! String ||
      !_screenRecoveryId.hasMatch(id) ||
      !const {'created', 'active', 'paused', 'stopped'}
          .contains(row['state']) ||
      binding is! Map ||
      binding['session_ref'] != requested['body_session_ref'] ||
      binding['instrument_ref'] != requested['instrument_ref'] ||
      row['destination'] != requested['destination'] ||
      row['model'] != requested['model'] ||
      row['delivery_mode'] != requested['delivery_mode'] ||
      sources is! List ||
      sources.isEmpty ||
      sources.length > 16 ||
      sources.any((id) => id is! String || !_screenRecoveryId.hasMatch(id)) ||
      sources.toSet().length != sources.length ||
      wanted is! List ||
      wanted.length != sources.length ||
      wanted.any((s) => s is! Map || s['source_id'] is! String) ||
      !sources.toSet().containsAll(wanted.map((s) => s['source_id']))) {
    throw const FormatException(
        'Recovered screen binding does not match request');
  }
  return Map.unmodifiable(row);
}

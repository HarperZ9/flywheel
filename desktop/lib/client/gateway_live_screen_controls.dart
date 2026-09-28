part of 'gateway_client.dart';

/// Dispatches an already approved operation. This API cannot prepare or mint a
/// grant; callers use the existing GatewayOperationScope review flow first.
extension GatewayLiveScreenControls on GatewayClient {
  /// Owner-authenticated revocation cannot open, resume, or deliver capture.
  Future<Map<String, dynamic>> revokeLiveScreen(
      String sessionId, String action) async {
    if (!const {'pause', 'stop'}.contains(action)) {
      throw const FormatException('Invalid screen revocation');
    }
    final result = await postJsonNoRedirect(
        '/api/live-screen/sessions/${_screenSegment(sessionId)}/$action', {});
    if (result['session_id'] != sessionId ||
        result['state'] != (action == 'stop' ? 'stopped' : 'paused')) {
      throw const FormatException('Screen revocation acknowledgement mismatch');
    }
    return result;
  }

  Future<Map<String, dynamic>> liveScreenControl(
      Map<String, dynamic> authorizedBody) async {
    final body = jsonDecode(jsonEncode(authorizedBody)) as Map<String, dynamic>;
    final control = body['control'];
    final grant = body['grant_ref'];
    if (body['schema'] != gatewayOperationSchema ||
        grant is! String ||
        !RegExp(r'^gnt_[0-9a-f]{32}$').hasMatch(grant) ||
        !const {'open', 'start', 'pause', 'resume', 'stop'}.contains(control)) {
      throw const FormatException('Approved screen operation required');
    }
    final session = body['session_id'];
    if (control != 'open' && session is! String) {
      throw const FormatException('Screen session required');
    }
    if (control == 'open') {
      _checkRequestedScreenSources(body['sources']);
      if (body.containsKey('start_immediately') &&
          body['start_immediately'] is! bool) {
        throw const FormatException('Invalid immediate start selection');
      }
    }
    final path = control == 'open'
        ? '/api/live-screen/sessions'
        : '/api/live-screen/sessions/${_screenSegment(session as String)}/$control';
    final result = await postJsonNoRedirect(path, body);
    final expectedState = switch (control) {
      'open' => body['start_immediately'] == true ? 'active' : 'created',
      'start' || 'resume' => 'active',
      'pause' => 'paused',
      _ => 'stopped',
    };
    final authority = result['authority'];
    final resultId = result['session_id'];
    if (resultId is! String ||
        !_screenId.hasMatch(resultId) ||
        control != 'open' && resultId != session ||
        result['state'] != expectedState ||
        authority is! Map ||
        authority['action'] != 'live_screen.control' ||
        authority['grant_ref'] != grant) {
      throw const FormatException(
          'Screen control result does not match request');
    }
    if (control == 'open') _checkOpenedScreen(body, result);
    return result;
  }
}

void _checkRequestedScreenSources(Object? value) {
  if (value is! List || value.isEmpty || value.length > 16) {
    throw const FormatException('Selected screen sources required');
  }
  final ids = <String>{};
  for (final source in value) {
    final id = source is Map ? source['source_id'] : null;
    if (id is! String || !_screenId.hasMatch(id) || !ids.add(id)) {
      throw const FormatException('Invalid selected screen sources');
    }
  }
}

void _checkOpenedScreen(
    Map<String, dynamic> body, Map<String, dynamic> result) {
  final requested = body['sources'];
  final selected = result['source_ids'];
  final binding = result['body_binding'];
  if (binding is! Map ||
      body['body_session_ref'] is! String ||
      body['instrument_ref'] is! String ||
      binding['session_ref'] != body['body_session_ref'] ||
      binding['instrument_ref'] != body['instrument_ref'] ||
      requested is! List ||
      requested.isEmpty ||
      requested.any((row) => row is! Map || row['source_id'] is! String) ||
      selected is! List ||
      selected.any((id) => id is! String) ||
      selected.toSet().length != selected.length ||
      requested.length != selected.length ||
      !selected.toSet().containsAll(requested.map((row) => row['source_id'])) ||
      result['destination'] != body['destination'] ||
      result['model'] != body['model'] ||
      result['delivery_mode'] != body['delivery_mode']) {
    throw const FormatException('Opened screen session binding mismatch');
  }
}

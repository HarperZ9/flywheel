part of 'gateway_client.dart';

/// Read-only observation of an already authorized screen session.
/// Listing sources or rendering this preview never creates a capture session.
extension GatewayLiveScreen on GatewayClient {
  Future<List<LiveScreenSource>> liveScreenSources() async {
    final data = await getJson('/api/live-screen/sources');
    final rows = data['sources'];
    if (rows is! List ||
        rows.length > 256 ||
        rows.any((row) => row is! Map<String, dynamic>)) {
      throw const FormatException('Screen source inventory unavailable');
    }
    final sources = rows
        .map((row) => LiveScreenSource.fromJson(row as Map<String, dynamic>))
        .toList();
    if (sources.any((source) => !_screenId.hasMatch(source.id)) ||
        sources.map((source) => source.id).toSet().length != sources.length) {
      throw const FormatException('Screen source inventory is ambiguous');
    }
    return List.unmodifiable(sources);
  }

  Future<Map<String, dynamic>> liveScreenStatus(String sessionId) =>
      getJson('/api/live-screen/sessions/${_screenSegment(sessionId)}');

  /// Observe the bounded event queue. The backend producer owns capture cadence;
  /// this request must never advance capture or trigger model inference.
  Stream<Map<String, dynamic>> liveScreenEvents(String sessionId) async* {
    final path = '/api/live-screen/sessions/${_screenSegment(sessionId)}/poll';
    while (true) {
      final request = http.Request('POST', Uri.parse('$baseUrl$path'))
        ..followRedirects = false
        ..headers['Content-Type'] = 'application/json'
        ..body = '{}';
      final response =
          await _http.send(request).timeout(const Duration(seconds: 5));
      if (response.statusCode != 200) {
        await response.stream.listen(null).cancel();
        throw const FormatException('Screen event feed unavailable');
      }
      final bytes = await _screenResponseBytes(response, 1024 * 1024);
      final body = jsonDecode(utf8.decode(bytes));
      final events = body is Map ? body['events'] : null;
      if (events is! List ||
          events.length > 1024 ||
          events.any((event) => event is! Map<String, dynamic>)) {
        throw const FormatException('Malformed screen event feed');
      }
      for (final event in events.cast<Map<String, dynamic>>()) {
        if (event['session_id'] != sessionId) {
          throw const FormatException('Screen event session mismatch');
        }
        yield event;
        if (event['event'] == 'screen.stop' ||
            event['event'] == 'screen.error' ||
            event['event'] == 'screen.session' && event['state'] == 'stopped') {
          return;
        }
      }
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
  }

  Future<Uint8List> liveScreenPreview(LiveScreenFrame frame) async {
    if (!frame.valid || frame.width * frame.height > 16777216) {
      throw const FormatException('Invalid screen preview identity');
    }
    final path = '/api/live-screen/sessions/'
        '${_screenSegment(frame.sessionId)}/sources/'
        '${_screenSegment(frame.sourceId)}/frames/${frame.sequence}/preview';
    final request = http.Request('GET', Uri.parse('$baseUrl$path'))
      ..followRedirects = false;
    final response =
        await _http.send(request).timeout(const Duration(seconds: 5));
    return _readScreenPreview(response, frame);
  }
}

final _screenId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,127}$');
String _screenSegment(String id) {
  if (!_screenId.hasMatch(id)) {
    throw const FormatException('Invalid screen session reference');
  }
  return Uri.encodeComponent(id);
}

Future<Uint8List> _readScreenPreview(
    http.StreamedResponse response, LiveScreenFrame frame) async {
  const maxBytes = 4 * 1024 * 1024;
  final mediaType = response.headers['content-type']?.split(';').first.trim();
  final declared = response.contentLength;
  if (response.statusCode != 200 ||
      !const {'image/png', 'image/jpeg'}.contains(mediaType) ||
      (declared != null && declared > maxBytes)) {
    await response.stream.listen(null).cancel();
    throw const FormatException('Screen preview unavailable');
  }
  final payload = await _screenResponseBytes(response, maxBytes);
  if (payload.isEmpty ||
      crypto.sha256.convert(payload).toString() != frame.digest) {
    throw const FormatException('Screen preview does not match frame identity');
  }
  return payload;
}

Future<Uint8List> _screenResponseBytes(
    http.StreamedResponse response, int maxBytes) async {
  final bytes = BytesBuilder(copy: false);
  final chunks = StreamIterator(response.stream);
  final clock = Stopwatch()..start();
  try {
    while (true) {
      final remaining = const Duration(seconds: 5) - clock.elapsed;
      if (remaining <= Duration.zero) {
        throw TimeoutException('Screen preview timed out');
      }
      if (!await chunks.moveNext().timeout(remaining)) break;
      final chunk = chunks.current;
      if (bytes.length + chunk.length > maxBytes) {
        throw const FormatException('Screen response exceeds size limit');
      }
      bytes.add(chunk);
    }
  } finally {
    await chunks.cancel();
  }
  return bytes.takeBytes();
}

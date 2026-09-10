import 'dart:async';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:flywheel_desktop/client/strict_plan_json.dart';

class ActorTransportError implements Exception {
  const ActorTransportError(this.code);
  final String code;
  @override
  String toString() => code;
}

Uri actorOrigin(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.scheme != 'http' ||
      !{'127.0.0.1', '::1'}.contains(uri.host) ||
      !uri.hasPort ||
      uri.port < 1 ||
      uri.port > 65535 ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/')) {
    throw const ActorTransportError('origin_denied');
  }
  return uri.replace(path: '');
}

/// One request per approved route, with no redirect or application retry.
/// The byte ceiling covers bodies, not raw HTTP framing. Timeout closes the
/// owned client; the supervisor remains the final process lifetime fence.
final class ActorGatewayTransport extends http.BaseClient {
  ActorGatewayTransport(Uri origin, this._token,
      {http.BaseClient? inner,
      this.maxBytes = 65536,
      Duration timeout = const Duration(seconds: 10),
      this.onEvent})
      : origin = actorOrigin(origin.toString()),
        _timeout = timeout,
        _inner = inner ?? IOClient(HttpClient()..findProxy = (_) => 'DIRECT') {
    if (maxBytes < 1 ||
        maxBytes > 1048576 ||
        timeout <= Duration.zero ||
        timeout > const Duration(seconds: 15) ||
        _token.isEmpty ||
        _token.contains('\r') ||
        _token.contains('\n')) {
      close();
      throw const ActorTransportError('transport_config_invalid');
    }
  }
  final Uri origin;
  final String _token;
  final http.BaseClient _inner;
  final int maxBytes;
  Duration _timeout;
  void restrictTimeout(Duration limit) {
    if (limit <= Duration.zero || limit > const Duration(seconds: 15)) {
      throw const ActorTransportError('deadline_invalid');
    }
    if (limit < _timeout) _timeout = limit;
  }

  final void Function(String stage, String path)? onEvent;
  final _used = <String>{};
  bool _closed = false;
  bool recordingFailed = false;
  void _record(String stage, String path) {
    try {
      onEvent?.call(stage, path);
    } on Object {
      recordingFailed = true;
      throw const ActorTransportError('recorder_failed');
    }
  }

  static const routes = {
    '/api/gateway-grants/capabilities',
    '/api/gateway-grants/prepare/lane.call',
    '/api/gateway-grants/read',
    '/api/gateway-grants/approve-reviewed-once',
    '/api/gateway-grants/reject',
    '/api/lane/bulletin/board_write_post',
  };

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final uri = request.url;
    if (_closed ||
        request is! http.Request ||
        request.method != 'POST' ||
        uri.scheme != origin.scheme ||
        uri.host != origin.host ||
        uri.port != origin.port ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        !routes.contains(uri.path) ||
        _used.contains(uri.path) ||
        request.bodyBytes.length > maxBytes) {
      throw const ActorTransportError('request_denied');
    }
    _used.add(uri.path); // Nonrefundable, including recorder failure.
    request.followRedirects = false;
    request.maxRedirects = 0;
    request.persistentConnection = false;
    request.headers['authorization'] = 'Bearer $_token';
    try {
      _record('request_entered', uri.path);
      return await _receive(request).timeout(_timeout);
    } on Object {
      close();
      throw const ActorTransportError('transport_incomplete');
    }
  }

  Future<http.StreamedResponse> _receive(http.BaseRequest request) async {
    final response = await _inner.send(request);
    if (response.statusCode >= 300 && response.statusCode < 400 ||
        (response.contentLength ?? 0) > maxBytes) {
      throw const ActorTransportError('response_denied');
    }
    final bytes = <int>[];
    await for (final chunk in response.stream) {
      if (_closed || bytes.length + chunk.length > maxBytes) {
        throw const ActorTransportError('response_denied');
      }
      bytes.addAll(chunk);
    }
    if (_closed) throw const ActorTransportError('transport_closed');
    _record('response_received', request.url.path);
    strictPlanJsonObject(
        bytes); // Reject duplicate keys before production parsing.
    return http.StreamedResponse(Stream.value(bytes), response.statusCode,
        headers: response.headers,
        contentLength: bytes.length,
        request: request,
        reasonPhrase: response.reasonPhrase);
  }

  @override
  void close() {
    _closed = true;
    _inner.close();
  }
}

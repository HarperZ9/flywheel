import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'voice.dart';

/// Optional client for the private Rowan local TTS daemon.
///
/// The adapter submits text to a loopback renderer, tracks the job, and can hand
/// the completed WAV receipt to an injected callback. It does not play audio
/// itself, and the shell does not wire it by default. A later platform layer can
/// decide how to play or cache the generated file.
class LocalTtsVoiceOutput implements VoiceOutput {
  LocalTtsVoiceOutput({
    required String token,
    String baseUrl = defaultBaseUrl,
    http.Client? httpClient,
    this.profile = 'rowan-draft-adjustable-20260915',
    this.voicePrompt,
    this.waitForAudio = true,
    this.timeout = const Duration(seconds: 120),
    this.pollInterval = const Duration(milliseconds: 250),
    this.onJobSubmitted,
    this.onAudioReady,
  })  : token = token.trim(),
        baseUri = Uri.parse(_trimSlash(baseUrl)),
        _http = httpClient ?? http.Client(),
        _ownsClient = httpClient == null {
    if (this.token.isEmpty) {
      throw ArgumentError.value(token, 'token', 'must not be empty');
    }
    if (!isLoopbackBaseUrl(baseUri)) {
      throw ArgumentError.value(baseUrl, 'baseUrl', 'must be loopback');
    }
  }

  static const defaultBaseUrl = 'http://127.0.0.1:8798';
  static const maxTextChars = 1000;
  static const maxResponseBytes = 65536;
  static final _jobIdPattern = RegExp(r'^tts_[0-9a-f]{32}$');

  final Uri baseUri;
  final String token;
  final http.Client _http;
  final bool _ownsClient;
  final String profile;
  final String? voicePrompt;
  final bool waitForAudio;
  final Duration timeout;
  final Duration pollInterval;
  final FutureOr<void> Function(String jobId)? onJobSubmitted;
  final FutureOr<void> Function(LocalTtsSpeakResult result)? onAudioReady;
  LocalTtsSpeakResult? lastResult;
  bool _closed = false;

  static bool isLoopbackBaseUrl(Uri uri) {
    if (uri.scheme != 'http') return false;
    return uri.host == '127.0.0.1' ||
        uri.host == 'localhost' ||
        uri.host == '::1';
  }

  @override
  Future<void> speak(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    final result = await synthesize(trimmed);
    lastResult = result;
    if (result.audioPath != null) {
      await onAudioReady?.call(result);
    }
  }

  Future<LocalTtsSpeakResult> synthesize(String text) async {
    _checkOpen();
    if (text.length > maxTextChars) {
      throw ArgumentError.value(text.length, 'text.length', 'exceeds limit');
    }
    final body = <String, Object?>{
      'text': text,
      'profile': profile,
      'wait': waitForAudio,
      'timeout_s': timeout.inSeconds,
      if (voicePrompt != null) 'voice_prompt': voicePrompt,
    };
    var result = await _sendJson('POST', '/v1/speak', body);
    final jobId = _jobId(result);
    await onJobSubmitted?.call(jobId);
    _checkAdvertisedJobRoute(result, jobId);
    if (waitForAudio) {
      result = await _waitForTerminal(result, jobId);
    }
    return LocalTtsSpeakResult.fromJson(result);
  }

  Future<LocalTtsSpeakResult> cancelLast() async {
    final jobId = lastResult?.jobId;
    if (jobId == null) {
      throw StateError('no local TTS job has been submitted');
    }
    return cancelJob(jobId);
  }

  Future<LocalTtsSpeakResult> cancelJob(String jobId) async {
    _checkOpen();
    final route = _jobRoute(jobId, suffix: '/cancel');
    final result = await _sendJson('POST', route, null);
    _ensureSameJobId(result, jobId);
    return LocalTtsSpeakResult.fromJson(result);
  }

  Future<Map<String, dynamic>> _waitForTerminal(
    Map<String, dynamic> first,
    String jobId,
  ) async {
    var result = first;
    final route = _jobRoute(jobId);
    final deadline = DateTime.now().add(timeout);
    while (!_terminal(result['state'])) {
      if (!DateTime.now().isBefore(deadline)) {
        throw TimeoutException('local TTS job did not finish', timeout);
      }
      await Future<void>.delayed(pollInterval);
      result = await _sendJson('GET', route, null);
      _ensureSameJobId(result, jobId);
      _checkAdvertisedJobRoute(result, jobId);
    }
    if (result['state'] != 'completed') {
      throw LocalTtsException('local TTS job ended as ${result['state']}');
    }
    return result;
  }

  Future<Map<String, dynamic>> _sendJson(
    String method,
    String route,
    Map<String, Object?>? body,
  ) async {
    _checkOpen();
    final request = http.Request(method, _routeUri(route))
      ..followRedirects = false
      ..maxRedirects = 0
      ..headers.addAll(_headers);
    if (body != null) {
      request.body = jsonEncode(body);
    }
    final response = await _http.send(request).timeout(timeout);
    final responseBody = await _readBoundedBody(response);
    return _decode(response.statusCode, responseBody);
  }

  Future<String> _readBoundedBody(http.StreamedResponse response) async {
    final builder = BytesBuilder(copy: false);
    var total = 0;
    await for (final chunk in response.stream.timeout(timeout)) {
      total += chunk.length;
      if (total > maxResponseBytes) {
        throw const FormatException('local TTS response exceeded byte limit');
      }
      builder.add(chunk);
    }
    return utf8.decode(builder.takeBytes());
  }

  Uri _routeUri(String route) {
    if (!route.startsWith('/') ||
        route.startsWith('//') ||
        route.contains(r'\')) {
      throw const FormatException(
          'local TTS route must be a relative API path');
    }
    final uri = baseUri.resolve(route);
    if (!isLoopbackBaseUrl(uri) ||
        uri.scheme != baseUri.scheme ||
        uri.host != baseUri.host ||
        uri.port != baseUri.port) {
      throw const FormatException('local TTS route left loopback service');
    }
    return uri;
  }

  String _jobRoute(String jobId, {String suffix = ''}) {
    if (!_jobIdPattern.hasMatch(jobId)) {
      throw const FormatException('local TTS job id is invalid');
    }
    return '/v1/jobs/$jobId$suffix';
  }

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      };

  Map<String, dynamic> _decode(int statusCode, String body) {
    final decoded = jsonDecode(body);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('local TTS response was not an object');
    }
    if (statusCode != 200 && statusCode != 202) {
      throw LocalTtsException(
        decoded['message']?.toString() ?? 'local TTS request failed',
      );
    }
    return decoded;
  }

  void close() {
    if (_closed) return;
    _closed = true;
    if (_ownsClient) _http.close();
  }

  void dispose() => close();

  void _checkOpen() {
    if (_closed) {
      throw StateError('local TTS client is closed');
    }
  }

  String _jobId(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    if (jobId is! String || !_jobIdPattern.hasMatch(jobId)) {
      throw const FormatException('local TTS job id missing or invalid');
    }
    return jobId;
  }

  void _ensureSameJobId(Map<String, dynamic> json, String expectedJobId) {
    if (_jobId(json) != expectedJobId) {
      throw const FormatException('local TTS job id changed');
    }
  }

  void _checkAdvertisedJobRoute(Map<String, dynamic> json, String jobId) {
    final jobUrl = json['job_url'];
    if (jobUrl == null) return;
    if (jobUrl is! String || jobUrl != _jobRoute(jobId)) {
      throw const FormatException('local TTS job URL did not match issued job');
    }
  }
}

class LocalTtsSpeakResult {
  LocalTtsSpeakResult({
    required this.jobId,
    required this.state,
    this.audioPath,
    this.manifestPath,
  }) {
    if (!LocalTtsVoiceOutput._jobIdPattern.hasMatch(jobId)) {
      throw const FormatException('local TTS job id is invalid');
    }
  }

  factory LocalTtsSpeakResult.fromJson(Map<String, dynamic> json) {
    return LocalTtsSpeakResult(
      jobId: json['job_id']?.toString() ?? '',
      state: json['state']?.toString() ?? '',
      audioPath: json['audio_path']?.toString(),
      manifestPath: json['manifest_path']?.toString(),
    );
  }

  final String jobId;
  final String state;
  final String? audioPath;
  final String? manifestPath;
}

class LocalTtsException implements Exception {
  const LocalTtsException(this.message);
  final String message;

  @override
  String toString() => 'LocalTtsException: $message';
}

bool _terminal(Object? state) {
  return state == 'completed' || state == 'cancelled' || state == 'failed';
}

String _trimSlash(String value) {
  return value.endsWith('/') ? value.substring(0, value.length - 1) : value;
}

// evidence_extensions_client.dart -- the typed client for the contextual
// extension routes. Every call decodes defensively; a typed transport
// error carries the gateway's fixed code, never a traceback.
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/evidence_extensions.dart';
import 'gateway_auth.dart';

class EvidenceExtensionsClient {
  final String baseUrl;
  final http.Client _http;

  EvidenceExtensionsClient({String? baseUrl, http.Client? httpClient})
      : baseUrl = baseUrl ?? 'http://127.0.0.1:8799',
        _http = httpClient ?? AuthedClient(http.Client());

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> body) async {
    final http.Response r;
    try {
      r = await _http.post(
        Uri.parse('$baseUrl$path'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );
    } catch (_) {
      throw const EvidenceExtensionFailure(
          'ENGINE_UNREACHABLE', 'the engine is unreachable');
    }
    if (r.statusCode != 200) {
      final decoded = _tryDecode(r);
      final err = decoded['error'];
      throw EvidenceExtensionFailure(
          err is Map<String, dynamic> && err['code'] is String
              ? err['code'] as String
              : 'INVALID_RESPONSE',
          'the extension request was refused');
    }
    return _tryDecode(r);
  }

  Map<String, dynamic> _tryDecode(http.Response r) {
    try {
      final v = jsonDecode(r.body);
      if (v is Map<String, dynamic>) return v;
    } catch (_) {}
    return {};
  }

  Future<EvidenceCapabilities> capabilities(String journeyRef) async {
    final http.Response r;
    try {
      r = await _http.get(Uri.parse(
          '$baseUrl/api/journeys/extensions/capabilities?ref=$journeyRef'));
    } catch (_) {
      throw const EvidenceExtensionFailure(
          'ENGINE_UNREACHABLE', 'the engine is unreachable');
    }
    final decoded = _tryDecode(r);
    return EvidenceCapabilities.fromJson(decoded);
  }

  Future<IncidentProposal?> incidentPropose({
    required String journeyRef,
    required String eventHeadSha256,
    required String capabilitySha256,
    required Map<String, dynamic> incidentCase,
    required List<Map<String, dynamic>> facts,
  }) async {
    final decoded = await _post('/api/journeys/extensions/incident-propose', {
      'journey_ref': journeyRef,
      'event_head_sha256': eventHeadSha256,
      'capability_sha256': capabilitySha256,
      'case': incidentCase,
      'projection': {
        'journey_ref': journeyRef,
        'event_head_sha256': eventHeadSha256,
        'facts': facts,
      },
    });
    return IncidentProposal.fromJson(decoded);
  }

  Future<FrontierAxes?> frontierProject({
    required String journeyRef,
    required String eventHeadSha256,
    required String capabilitySha256,
    required Map<String, dynamic> claim,
  }) async {
    final decoded = await _post(
        '/api/journeys/extensions/frontier-project',
        {
          'journey_ref': journeyRef,
          'event_head_sha256': eventHeadSha256,
          'capability_sha256': capabilitySha256,
          'claim': claim,
        });
    return FrontierAxes.fromJson(decoded);
  }

  Future<DomainPackProjection?> domainPackProject({
    required String capabilitySha256,
    required Map<String, dynamic> manifest,
    required List<Map<String, dynamic>> fixtures,
  }) async {
    final decoded = await _post(
        '/api/journeys/extensions/domain-pack-project',
        {
          'capability_sha256': capabilitySha256,
          'manifest': manifest,
          'fixtures': fixtures,
        });
    return DomainPackProjection.fromJson(decoded);
  }
}

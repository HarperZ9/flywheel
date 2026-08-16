part of 'gateway_client.dart';

enum GatewayOperationEventType { snapshot, progress, terminal, done }

final class GatewayOperationEvent {
  final int sequence;
  final GatewayOperationEventType type;
  final OperationSnapshot? snapshot;
  final OperationResult? result;
  final Map<String, dynamic>? progress;
  const GatewayOperationEvent._(
      this.sequence, this.type, this.snapshot, this.result, this.progress);
  bool get isDone => type == GatewayOperationEventType.done;
}

final class GatewayOperations {
  final GatewayClient _client;
  const GatewayOperations(this._client);

  Stream<GatewayOperationEvent> start(Map<String, dynamic> authorizedBody) {
    final encoded = utf8.encode(jsonEncode(authorizedBody));
    if (encoded.length > 1048576) {
      return Stream.error(const GatewaySseException());
    }
    final request =
        http.Request('POST', Uri.parse('${_client.baseUrl}/api/agent'))
          ..headers['Content-Type'] = 'application/json'
          ..bodyBytes = encoded;
    return _events(request);
  }

  Stream<GatewayOperationEvent> watch(String operationRef,
      {int afterSequence = 0}) {
    _validateRef(operationRef);
    if (afterSequence < 0) throw ArgumentError('Invalid operation watch');
    final path = '/api/operations/$operationRef/events?after=$afterSequence';
    return _events(http.Request('GET', Uri.parse('${_client.baseUrl}$path')),
        afterSequence: afterSequence);
  }

  Future<OperationSnapshot> snapshot(String operationRef) async {
    _validateRef(operationRef);
    final response = await _client._http
        .get(Uri.parse('${_client.baseUrl}/api/operations/$operationRef'));
    return OperationSnapshot.fromJson(
        Map<String, Object?>.from(_client._decode(response)));
  }

  Future<OperationResult> result(String operationRef) async {
    _validateRef(operationRef);
    final terminal = await snapshot(operationRef);
    if (!terminal.isTerminal) throw const GatewaySseException();
    final response = await _client._http.get(
        Uri.parse('${_client.baseUrl}/api/operations/$operationRef/result'));
    final result = OperationResult.fromJson(
        Map<String, Object?>.from(_client._decode(response)));
    if (!_matchingTerminal(terminal, result)) throw const GatewaySseException();
    return result;
  }

  Future<OperationSnapshot> cancel(Map<String, dynamic> finalBody) async {
    final encoded = utf8.encode(jsonEncode(finalBody));
    if (encoded.length > 1048576) throw const GatewaySseException();
    final response = await _client._http.post(
        Uri.parse('${_client.baseUrl}/api/operations/cancel'),
        headers: {'Content-Type': 'application/json'},
        body: encoded);
    return OperationSnapshot.fromJson(
        Map<String, Object?>.from(_client._decode(response)));
  }

  Stream<GatewayOperationEvent> _events(http.Request request,
      {int afterSequence = 0}) async* {
    final response = await _client._http.send(request);
    if (response.statusCode != 200) {
      final body = await _boundedResponse(response.stream);
      throw GatewayException.fromResponse(response.statusCode, body);
    }
    await for (final event
        in response.stream.transform(const GatewaySseDecoder())) {
      if (event.id <= afterSequence) throw const GatewaySseException();
      try {
        yield _parseEvent(event);
      } on GatewaySseException {
        rethrow;
      } on Object {
        throw const GatewaySseException();
      }
    }
  }
}

Future<String> _boundedResponse(Stream<List<int>> stream) async {
  final bytes = <int>[];
  await for (final chunk in stream) {
    if (bytes.length + chunk.length > 1048576) {
      throw const GatewaySseException();
    }
    bytes.addAll(chunk);
  }
  try {
    return utf8.decode(bytes);
  } on Object {
    throw const GatewaySseException();
  }
}

GatewayOperationEvent _parseEvent(GatewaySseEvent event) {
  if (event.isDone) {
    return GatewayOperationEvent._(
        event.id, GatewayOperationEventType.done, null, null, null);
  }
  final data = event.data;
  if (data is! Map<String, dynamic>) throw const GatewaySseException();
  if (event.event == 'snapshot') {
    final snapshot =
        OperationSnapshot.fromJson(Map<String, Object?>.from(data));
    return GatewayOperationEvent._(
        event.id, GatewayOperationEventType.snapshot, snapshot, null, null);
  }
  if (event.event == 'progress') {
    return GatewayOperationEvent._(event.id, GatewayOperationEventType.progress,
        null, null, Map<String, dynamic>.unmodifiable(data));
  }
  if (event.event != 'terminal' ||
      data.length != 2 ||
      data['snapshot'] is! Map<String, dynamic> ||
      data['result'] is! Map<String, dynamic>) {
    throw const GatewaySseException();
  }
  final snapshot = OperationSnapshot.fromJson(
      Map<String, Object?>.from(data['snapshot'] as Map<String, dynamic>));
  final result = OperationResult.fromJson(
      Map<String, Object?>.from(data['result'] as Map<String, dynamic>));
  if (!_matchingTerminal(snapshot, result)) {
    throw const GatewaySseException();
  }
  return GatewayOperationEvent._(
      event.id, GatewayOperationEventType.terminal, snapshot, result, null);
}

bool _matchingTerminal(OperationSnapshot snapshot, OperationResult result) =>
    snapshot.isTerminal &&
    snapshot.operationRef == result.operationRef &&
    snapshot.state == result.state &&
    snapshot.resultSha256 == result.canonicalSha256;

void _validateRef(String value) {
  if (!RegExp(r'^op_[0-9a-f]{32}$').hasMatch(value)) {
    throw ArgumentError('Invalid operation reference');
  }
}

part of 'journey_api.dart';

const _fixedErrors = <String, (Set<int>, String)>{
  'AUTH_REQUIRED': ({401}, 'Journey authorization is required'),
  'PERMISSION_REQUIRED': ({403}, 'Journey approval is required'),
  'PERMISSION_DENIED': ({403}, 'Journey operation is not permitted'),
  'APPROVAL_EXPIRED': ({403}, 'Journey approval expired'),
  'JOURNEY_NOT_FOUND': ({404}, 'Journey was not found'),
  'HEAD_CONFLICT': ({409}, 'Journey state changed'),
  'VERSION_MISMATCH': ({409}, 'Journey data version is unavailable'),
  'IDEMPOTENCY_MISMATCH': ({409}, 'Journey request conflicts with prior use'),
  'INVALID_TRANSITION': ({409, 422}, 'Journey transition is unavailable'),
  'STORE_COMMIT_FAILED': ({500}, 'Journey persistence failed'),
  'STORE_BUSY': ({503}, 'Journey persistence is busy'),
  'CANCEL_UNAVAILABLE': ({409}, 'Journey cancellation is unavailable'),
};

JourneyFailure _localFailure([String code = 'INVALID_RESPONSE']) =>
    JourneyFailure(code,
        _fixedErrors[code]?.$2 ?? 'Gateway response was invalid', const []);

JourneyFailure _readFailure(Object? value) {
  final code = GatewayException.fromResponse(200, jsonEncode(value)).errorCode;
  return code != null && _fixedErrors.containsKey(code)
      ? _localFailure(code)
      : _localFailure();
}

JourneyFailure _gatewayFailure(Object error) {
  if (error is ClientException ||
      error is SocketException ||
      error is TimeoutException) {
    return JourneyFailure('GATEWAY_UNREACHABLE',
        'Gateway communication failed; the operation outcome is unknown.', []);
  }
  if (error is GatewayException && error.errorSchema == gatewayErrorSchema) {
    final code = error.errorCode;
    final fixed = _fixedErrors[code];
    if (code != null && fixed?.$1.contains(error.statusCode) == true) {
      return _localFailure(code);
    }
  }
  return _localFailure();
}

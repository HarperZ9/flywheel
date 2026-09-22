import 'package:flutter/foundation.dart';

import '../models/operation_models.dart';
import '../models/provider_session_models.dart';

final class ProviderSessionController extends ChangeNotifier {
  ProviderSessionState _state = const ProviderSessionState();
  ProviderSessionState get state => _state;

  void begin(String operationRef) => _set(_state.begin(operationRef));

  void acceptProgress(Map<String, dynamic> progress) {
    try {
      _set(_state.apply(ProviderSessionEvent.fromProgress(progress)));
    } on ArgumentError {
      // Gateway-controlled progress is defensive input. Malformed provider
      // state does not get to replace the last inspectable state.
    }
  }

  void acceptTerminal(OperationResult result) {
    if (!providerSessionActions.contains(result.action)) return;
    try {
      _set(_state.apply(ProviderSessionEvent.fromResult(result),
          terminal: true));
    } on ArgumentError {
      _set(ProviderSessionState(
          operationRef: result.operationRef, terminal: true));
    }
  }

  void _set(ProviderSessionState next) {
    _state = next;
    notifyListeners();
  }
}

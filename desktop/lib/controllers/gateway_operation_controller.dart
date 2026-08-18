import 'package:flutter/widgets.dart';

import '../client/gateway_grants.dart';
import '../models/gateway_grant_models.dart';
export '../models/gateway_grant_models.dart'
    show GatewayDestination, GatewayJourneyBinding, GatewayOperation;

typedef GatewayOperationSupplier = GatewayOperation? Function();
typedef GatewayJourneyBindingSupplier = GatewayJourneyBinding? Function();
typedef GatewayHeadConflictRefresh = Future<void> Function();
typedef GatewayOperationAuthorizer = Future<Object?> Function(
    BuildContext context,
    GatewayOperation operation,
    GatewayOperationSupplier currentOperation,
    Future<Object?> Function(Map<String, dynamic>) dispatch);

final class GatewayOperationFailure implements Exception {
  final String code, message;
  const GatewayOperationFailure(this.code, this.message);
}

final class GatewayAuthorizationOutcome<T> {
  final T? value;
  final GatewayOperationFailure? failure;
  final bool denied;
  const GatewayAuthorizationOutcome.value(T this.value)
      : failure = null,
        denied = false;
  const GatewayAuthorizationOutcome.failure(
      GatewayOperationFailure this.failure)
      : value = null,
        denied = false;
  const GatewayAuthorizationOutcome.denied()
      : value = null,
        failure = null,
        denied = true;
}

final class GatewayOperationScope extends InheritedWidget {
  const GatewayOperationScope(
      {super.key, required this.authorize, required super.child});
  final GatewayOperationAuthorizer authorize;
  static GatewayOperationScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<GatewayOperationScope>();
  @override
  bool updateShouldNotify(GatewayOperationScope oldWidget) =>
      authorize != oldWidget.authorize;
}

final class GatewayOperationController extends ChangeNotifier {
  final GatewayGrantClient _grants;
  GatewayOperationController(this._grants);

  GatewayGrantProposal? _proposal;
  GatewayOperation? _operation;
  GatewayJourneyBinding? _binding;
  GatewayOperationSupplier? _currentOperation;
  GatewayJourneyBindingSupplier? _currentBinding;
  GatewayHeadConflictRefresh? _refreshOnHeadConflict;
  GatewayOperationFailure? _failure;
  var _generation = 0, _lifetime = 0;
  bool _pending = false;

  GatewayGrantProposal? get proposal => _proposal;
  GatewayOperationFailure? get failure => _failure;
  bool get pending => _pending;

  Future<bool> prepare(GatewayOperation operation,
      {required GatewayJourneyBinding binding,
      required GatewayOperationSupplier currentOperation,
      required GatewayJourneyBindingSupplier currentBinding,
      GatewayHeadConflictRefresh? refreshOnHeadConflict}) async {
    if (_pending || _proposal != null) return false;
    final lifetime = ++_lifetime;
    final generation = ++_generation;
    _capture(operation, binding, currentOperation, currentBinding,
        refreshOnHeadConflict);
    _pending = true;
    notifyListeners();
    try {
      final result = await _grants.prepare(operation, binding: binding);
      if (generation != _generation) return false;
      if (!_matches(generation)) return _rejectChanged(notify: false);
      _proposal = result;
      return true;
    } on Object catch (error) {
      await _recordFailure(error, lifetime, generation);
      return false;
    } finally {
      _settle(lifetime);
    }
  }

  Future<T?> approveAndDispatch<T>(
      Future<T> Function(Map<String, dynamic> finalBody) dispatch) async {
    final proposal = _proposal;
    final operation = _operation;
    final binding = _binding;
    if (_pending || proposal == null || operation == null || binding == null) {
      return null;
    }
    final lifetime = _lifetime;
    final generation = _generation;
    if (!_matches(generation)) {
      _rejectChanged();
      return null;
    }
    _pending = true;
    notifyListeners();
    try {
      final approved = await _grants.approve(proposal.proposalRef);
      if (generation != _generation) return null;
      if (!_matches(generation)) {
        _rejectChanged(notify: false);
        return null;
      }
      if (approved.grantRef != proposal.plannedGrantRef) {
        throw const GatewayGrantException(
            'INVALID_RESPONSE', 'Gateway response was invalid');
      }
      if (!_matches(generation)) {
        _rejectChanged(notify: false);
        return null;
      }
      _proposal = null;
      return await dispatch(
          Map.unmodifiable(operation.finalBody(binding, approved.grantRef)));
    } on Object catch (error) {
      await _recordFailure(error, lifetime, generation);
      return null;
    } finally {
      _settle(lifetime);
    }
  }

  void invalidate() {
    _generation++;
    _clearCapture();
    _failure = null;
    notifyListeners();
  }

  void _capture(
      GatewayOperation operation,
      GatewayJourneyBinding binding,
      GatewayOperationSupplier operationSupplier,
      GatewayJourneyBindingSupplier bindingSupplier,
      GatewayHeadConflictRefresh? refresh) {
    _proposal = null;
    _failure = null;
    _operation = operation;
    _binding = binding;
    _currentOperation = operationSupplier;
    _currentBinding = bindingSupplier;
    _refreshOnHeadConflict = refresh;
  }

  bool _matches(int generation) {
    try {
      return generation == _generation &&
          _operation == _currentOperation?.call() &&
          _binding == _currentBinding?.call();
    } on Object {
      return false;
    }
  }

  bool _rejectChanged({bool notify = true}) {
    _proposal = null;
    _failure = const GatewayOperationFailure(
        'OPERATION_CHANGED', 'Operation changed; approval was not used');
    if (notify) notifyListeners();
    return false;
  }

  Future<void> _recordFailure(
      Object error, int lifetime, int generation) async {
    if (generation != _generation) return;
    final safe = gatewayGrantFailure(error);
    final failure = GatewayOperationFailure(safe.code, safe.message);
    if (failure.code == 'HEAD_CONFLICT') {
      try {
        await _refreshOnHeadConflict?.call();
      } on Object {
        // The fixed gateway failure remains the visible outcome.
      }
    }
    if (lifetime == _lifetime && generation == _generation) {
      _proposal = null;
      _failure = failure;
    }
  }

  void _settle(int lifetime) {
    if (lifetime != _lifetime) return;
    _pending = false;
    notifyListeners();
  }

  void _clearCapture() {
    _proposal = null;
    _operation = null;
    _binding = null;
    _currentOperation = null;
    _currentBinding = null;
    _refreshOnHeadConflict = null;
  }
}

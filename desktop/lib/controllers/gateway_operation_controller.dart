import 'dart:convert';

import 'package:flutter/widgets.dart';

import '../client/gateway_grants.dart';
import '../models/gateway_grant_models.dart';
export '../models/gateway_grant_models.dart' show GatewayOperation;

typedef GatewayOperationAuthorizer = Future<Object?> Function(
    BuildContext context,
    GatewayOperation operation,
    Future<Object?> Function(Map<String, dynamic>) dispatch);

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
  String? _journeyRef, _eventHead;
  Object? _failure;
  var _generation = 0;
  bool _pending = false;

  GatewayGrantProposal? get proposal => _proposal;
  Object? get failure => _failure;
  bool get pending => _pending;

  Future<bool> prepare(GatewayOperation operation,
      {required String journeyRef, required String eventHead}) async {
    final generation = ++_generation;
    _proposal = null;
    _failure = null;
    _operation = operation;
    _journeyRef = journeyRef;
    _eventHead = eventHead;
    _pending = true;
    notifyListeners();
    try {
      final result = await _grants.prepare(operation,
          journeyRef: journeyRef, eventHead: eventHead);
      if (generation != _generation) return false;
      _proposal = result;
      return true;
    } on Object catch (error) {
      if (generation == _generation) {
        _failure = error;
      }
      return false;
    } finally {
      if (generation == _generation) {
        _pending = false;
        notifyListeners();
      }
    }
  }

  bool stillMatches(GatewayOperation operation,
          {required String journeyRef, required String eventHead}) =>
      _proposal != null &&
      _journeyRef == journeyRef &&
      _eventHead == eventHead &&
      _sameOperation(_operation, operation);

  Future<T?> approveAndDispatch<T>(
      Future<T> Function(Map<String, dynamic> finalBody) dispatch) async {
    final proposal = _proposal;
    final operation = _operation;
    final journeyRef = _journeyRef;
    final eventHead = _eventHead;
    if (_pending ||
        proposal == null ||
        operation == null ||
        journeyRef == null ||
        eventHead == null) {
      return null;
    }
    final generation = _generation;
    _pending = true;
    notifyListeners();
    try {
      final approved = await _grants.approve(proposal.proposalRef);
      if (generation != _generation ||
          approved.grantRef != proposal.plannedGrantRef) {
        throw const GatewayGrantException(
            'INVALID_RESPONSE', 'Gateway response was invalid');
      }
      final body =
          operation.finalBody(journeyRef, eventHead, approved.grantRef);
      _proposal = null;
      return await dispatch(Map.unmodifiable(body));
    } on Object catch (error) {
      if (generation == _generation) {
        _failure = error;
      }
      return null;
    } finally {
      if (generation == _generation) {
        _pending = false;
        notifyListeners();
      }
    }
  }

  void invalidate() {
    _generation++;
    _proposal = null;
    _operation = null;
    _journeyRef = null;
    _eventHead = null;
    _failure = null;
    _pending = false;
    notifyListeners();
  }
}

bool _sameOperation(GatewayOperation? left, GatewayOperation right) =>
    left != null &&
    left.action == right.action &&
    left.clientRequestId == right.clientRequestId &&
    jsonEncode(left.operation) == jsonEncode(right.operation);

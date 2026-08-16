import 'package:flutter/foundation.dart';

import '../client/gateway_grants.dart';
import '../client/gateway_plan.dart';
import '../models/plan_run_models.dart';
import 'gateway_operation_controller.dart';

const planRunCompletionCopy =
    'Run recorded. This receipt binds the forged contract; it does not say the listed gates ran or passed.';
const planRunDriftCopy =
    'Run blocked: this plan no longer matches its stored forge contract. Review it and forge again.';

enum PlanPhase {
  idle,
  forging,
  ready,
  approvalRequired,
  running,
  completed,
  drift,
  failed;

  String get wireName => switch (this) {
        PlanPhase.approvalRequired => 'approval_required',
        _ => name,
      };
}

typedef PlanAuthorizer
    = Future<GatewayAuthorizationOutcome<PlanRunResult>> Function(
        GatewayOperation operation,
        GatewayOperationSupplier currentOperation,
        Future<PlanRunResult> Function(Map<String, dynamic>) dispatch);

final class PlanRunRequest {
  final String workflow, profile, root, endpoint, clientRequestId;
  final bool allowWrite, allowExec;
  final String? testCmd;
  final PlanRunBinding binding;
  final List<String> dataRefs, credentialRefs;

  PlanRunRequest(
      {required this.workflow,
      required this.profile,
      required this.root,
      required this.endpoint,
      required this.allowWrite,
      required this.allowExec,
      required this.binding,
      required List<String> dataRefs,
      required List<String> credentialRefs,
      required this.clientRequestId,
      this.testCmd})
      : dataRefs = List.unmodifiable(dataRefs),
        credentialRefs = List.unmodifiable(credentialRefs);

  GatewayOperation get operation => GatewayOperation.exact(
        action: 'plan.run',
        clientRequestId: clientRequestId,
        operation: {
          'workflow': workflow,
          'profile': profile,
          'root': root,
          'endpoint': endpoint,
          'allow_write': allowWrite,
          'allow_exec': allowExec,
          if (testCmd != null) 'test_cmd': testCmd!,
          'binding': binding.toJson(),
        },
        dataRefs: dataRefs,
        credentialRefs: credentialRefs,
      );

  @override
  bool operator ==(Object other) =>
      other is PlanRunRequest &&
      workflow == other.workflow &&
      profile == other.profile &&
      root == other.root &&
      endpoint == other.endpoint &&
      allowWrite == other.allowWrite &&
      allowExec == other.allowExec &&
      testCmd == other.testCmd &&
      binding.bindingSha256 == other.binding.bindingSha256 &&
      listEquals(dataRefs, other.dataRefs) &&
      listEquals(credentialRefs, other.credentialRefs) &&
      clientRequestId == other.clientRequestId;

  @override
  int get hashCode => Object.hash(
      workflow,
      profile,
      root,
      endpoint,
      allowWrite,
      allowExec,
      testCmd,
      binding.bindingSha256,
      Object.hashAll(dataRefs),
      Object.hashAll(credentialRefs),
      clientRequestId);
}

final class PlanController extends ChangeNotifier {
  final GatewayPlan _gateway;
  PlanController(this._gateway);

  PlanPhase _phase = PlanPhase.idle;
  String _goal = '';
  PlanRunBinding? _binding;
  PlanRunRequest? _request;
  PlanRunResult? _result;
  GatewayOperationFailure? _failure;

  PlanPhase get phase => _phase;
  String get goal => _goal;
  PlanRunBinding? get binding => _binding;
  PlanRunRequest? get request => _request;
  PlanRunResult? get result => _result;
  GatewayOperationFailure? get failure => _failure;
  String? get completionMessage =>
      _phase == PlanPhase.completed ? planRunCompletionCopy : null;
  String? get failureMessage =>
      _phase == PlanPhase.drift ? planRunDriftCopy : _failure?.message;

  Future<bool> forge(String goal,
      {String? context,
      List<String>? examples,
      List<String>? documentation,
      String? intentSource,
      String? architectureSource}) async {
    final nextGoal = goal.trim();
    if (nextGoal.isEmpty ||
        _phase == PlanPhase.forging ||
        _phase == PlanPhase.running) {
      return false;
    }
    _goal = nextGoal;
    _request = null;
    _result = null;
    _failure = null;
    _setPhase(PlanPhase.forging);
    try {
      _binding = await _gateway.forge(nextGoal,
          context: context,
          examples: examples,
          documentation: documentation,
          intentSource: intentSource,
          architectureSource: architectureSource);
      _setPhase(PlanPhase.ready);
      return true;
    } on Object catch (error) {
      _failure = _safeFailure(error);
      _setPhase(PlanPhase.failed);
      return false;
    }
  }

  Future<void> run(PlanRunRequest next,
      {required PlanRunRequest? Function() currentRequest,
      required PlanAuthorizer authorize}) async {
    if (_binding == null ||
        next.binding.bindingSha256 != _binding!.bindingSha256 ||
        _phase == PlanPhase.forging ||
        _phase == PlanPhase.running ||
        _phase == PlanPhase.approvalRequired) {
      return;
    }
    _request = next;
    _result = null;
    _failure = null;
    final operation = next.operation;
    GatewayOperation? currentOperation() {
      try {
        return currentRequest()?.operation;
      } on Object {
        return null;
      }
    }

    _setPhase(PlanPhase.approvalRequired);
    GatewayOperationFailure? dispatchFailure;
    try {
      final outcome =
          await authorize(operation, currentOperation, (body) async {
        _setPhase(PlanPhase.running);
        try {
          return await _gateway.dispatch(body);
        } on Object catch (error) {
          dispatchFailure = _safeFailure(error);
          rethrow;
        }
      });
      final failure = dispatchFailure ?? outcome.failure;
      if (failure != null) {
        return _applyFailure(failure);
      }
      if (outcome.denied || outcome.value == null) {
        _setPhase(PlanPhase.ready);
        return;
      }
      if (outcome.value!.binding.bindingSha256 != _binding!.bindingSha256) {
        return _applyFailure(const GatewayOperationFailure(
            'INVALID_RESPONSE', 'Gateway response was invalid'));
      }
      _result = outcome.value;
      _setPhase(PlanPhase.completed);
    } on Object catch (error) {
      _applyFailure(dispatchFailure ?? _safeFailure(error));
    }
  }

  void invalidateRun() {
    if (_phase == PlanPhase.approvalRequired) {
      _failure = const GatewayOperationFailure(
          'OPERATION_CHANGED', 'Operation changed; approval was not used');
      _setPhase(PlanPhase.ready);
    }
  }

  void _applyFailure(GatewayOperationFailure failure) {
    _failure = failure;
    _setPhase(failure.code == 'PLAN_BINDING_DRIFT'
        ? PlanPhase.drift
        : failure.code == 'OPERATION_CHANGED'
            ? PlanPhase.ready
            : PlanPhase.failed);
  }

  GatewayOperationFailure _safeFailure(Object error) {
    if (error is GatewayOperationFailure) return error;
    final safe = gatewayGrantFailure(error);
    return GatewayOperationFailure(safe.code, safe.message);
  }

  void _setPhase(PlanPhase value) {
    _phase = value;
    notifyListeners();
  }
}

import 'package:flutter/foundation.dart';

import '../models/gateway_grant_models.dart';
import '../models/operation_models.dart';
import '../models/rowan_walkthrough_models.dart';

final class RowanWalkthroughController extends ChangeNotifier {
  RowanWalkthroughController({required this.scenario});

  final RowanWalkthroughScenario scenario;
  final List<Map<String, dynamic>> _events = [];
  String? _endpoint, _model, _root;
  OperationSnapshot? _snapshot;
  OperationResult? _terminalResult;
  RowanWalkthroughCheckpoint _checkpoint = RowanWalkthroughCheckpoint.readiness;
  RowanWalkthroughOracle _oracle = const RowanWalkthroughOracle(
    RowanWalkthroughOracleState.waiting,
    'The oracle runs only after a terminal result is available.',
  );
  RowanWalkthroughOutcome? _outcome;

  RowanWalkthroughCheckpoint get checkpoint => _checkpoint;
  RowanWalkthroughOracle get oracle => _oracle;
  RowanWalkthroughOutcome? get outcome => _outcome;
  OperationSnapshot? get snapshot => _snapshot;
  OperationResult? get terminalResult => _terminalResult;
  List<Map<String, dynamic>> get events => List.unmodifiable(_events);
  String? get endpoint => _endpoint;
  String? get selectedModel => _model;
  String? get root => _root;
  bool get ready =>
      (_endpoint?.isNotEmpty ?? false) &&
      (_model?.isNotEmpty ?? false) &&
      (_root?.trim().isNotEmpty ?? false);
  bool get canPrepareFollowUp =>
      _checkpoint == RowanWalkthroughCheckpoint.reopened && _oracle.passed;

  void selectEndpoint(String? value) {
    if (_endpoint == value) return;
    _endpoint = value;
    _model = null;
    _outcome = null;
    _rewindBeforeStart();
    notifyListeners();
  }

  void selectModel(String value) {
    _model = value.trim().isEmpty ? null : value.trim();
    _outcome = null;
    _rewindBeforeStart();
    notifyListeners();
  }

  void setRoot(String value) {
    _root = value.trim().isEmpty ? null : value.trim();
    _outcome = null;
    _rewindBeforeStart();
    notifyListeners();
  }

  GatewayOperation? operationFor(String requestId) {
    final endpoint = _endpoint;
    final root = _root;
    final model = _model;
    if (endpoint == null ||
        endpoint.isEmpty ||
        model == null ||
        model.isEmpty ||
        root == null ||
        root.isEmpty) {
      return null;
    }
    return GatewayOperation.exact(
      action: 'agent.run',
      clientRequestId: requestId,
      operation: {
        'goal': scenario.goal,
        'endpoint': endpoint,
        'model': model,
        'root': root,
        'max_steps': scenario.maxSteps,
        'max_tokens': scenario.maxTokens,
        'timeout_s': scenario.timeoutSeconds,
        'allow_write': false,
        'allow_exec': false,
        'stream': true,
      },
      dataRefs: const [],
      credentialRefs: const [],
    );
  }

  void markReviewPrepared() {
    if (!ready) return;
    _checkpoint = RowanWalkthroughCheckpoint.review;
    _outcome = null;
    notifyListeners();
  }

  void beginExecution() {
    _events.clear();
    _snapshot = null;
    _terminalResult = null;
    _checkpoint = RowanWalkthroughCheckpoint.running;
    _oracle = const RowanWalkthroughOracle(
      RowanWalkthroughOracleState.waiting,
      'The oracle runs only after a terminal result is available.',
    );
    _outcome = null;
    notifyListeners();
  }

  void markDenied() {
    if (_checkpoint.index < RowanWalkthroughCheckpoint.review.index) {
      _checkpoint = RowanWalkthroughCheckpoint.review;
    }
    _outcome = RowanWalkthroughOutcome.denied;
    notifyListeners();
  }

  void markInterrupted() {
    _outcome = RowanWalkthroughOutcome.interrupted;
    notifyListeners();
  }

  void acceptProgress(Map<String, dynamic> event) {
    _events.add(Map<String, dynamic>.unmodifiable(event));
    notifyListeners();
  }

  void acceptSnapshot(OperationSnapshot snapshot) {
    _snapshot = snapshot;
    if (!snapshot.isTerminal) {
      _checkpoint = RowanWalkthroughCheckpoint.running;
    }
    notifyListeners();
  }

  void acceptTerminalResult(OperationResult result) {
    _terminalResult = result;
    _events.add(Map<String, dynamic>.unmodifiable({
      ...result.result,
      'type': 'done',
    }));
    _oracle = scenario.evaluate(result.result);
    _checkpoint = RowanWalkthroughCheckpoint.semanticOracle;
    _outcome = _oracle.passed ? null : RowanWalkthroughOutcome.wrongAnswer;
    notifyListeners();
  }

  void markReopened(OperationSnapshot snapshot) {
    final terminal = _terminalResult;
    if (terminal == null ||
        !snapshot.isTerminal ||
        snapshot.operationRef != terminal.operationRef ||
        snapshot.resultSha256 != terminal.canonicalSha256 ||
        !_oracle.passed) {
      _outcome = RowanWalkthroughOutcome.missingRecord;
      notifyListeners();
      return;
    }
    _snapshot = snapshot;
    _checkpoint = RowanWalkthroughCheckpoint.reopened;
    _outcome = null;
    notifyListeners();
  }

  void _rewindBeforeStart() {
    if (_snapshot == null) {
      _checkpoint = RowanWalkthroughCheckpoint.readiness;
      _oracle = const RowanWalkthroughOracle(
        RowanWalkthroughOracleState.waiting,
        'The oracle runs only after a terminal result is available.',
      );
    }
  }
}

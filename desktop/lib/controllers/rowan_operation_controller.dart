import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/widgets.dart';

import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../models/agent_execution_mode.dart';
import '../models/agent_run_operation.dart';
import '../models/evidence_state.dart';
import '../models/agent_tool_protocol.dart';
import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../services/journey_session_store.dart';
import '../widgets/effort_dial.dart';
import '../widgets/operation_grant_sheet.dart';
import 'gateway_operation_controller.dart';
import 'operation_controller.dart';

part 'rowan_operation_controller_parts.dart';
part 'rowan_operation_builder.dart';
part 'rowan_session_locator.dart';

final _modelId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,159}$');

final class RowanOperationController extends ChangeNotifier {
  RowanOperationController(this.client, {JourneySessionStore? sessionStore})
      : _sessionStore = sessionStore,
        _operations = GatewayOperations(client),
        _stopGrants = GatewayOperationController(GatewayGrantClient(client)) {
    _operationState = _newRowanOperationState(this);
  }

  final GatewayClient client;
  final GatewayOperations _operations;
  final GatewayOperationController _stopGrants;
  final JourneySessionStore? _sessionStore;
  late OperationController _operationState;

  List<EndpointRow> _endpoints = const [];
  String? _endpoint, _selectedModel, _workspaceRoot, _error;
  AgentExecutionMode _executionMode = AgentExecutionMode.api;
  EffortLevel _effort = EffortLevel.standard;
  AgentToolProtocol _toolProtocol = AgentToolProtocol.compatibility;
  int _maxTokens = 1024, _timeoutSeconds = 300;
  int? _maxStepsOverride;
  bool _allowWrite = false, _allowExec = false, _authorizing = false;
  bool _recoveryBlocked = false;
  int _configGeneration = 0;
  String? _pendingRequestSha256;
  List<Map<String, dynamic>> _progress = const [];

  List<EndpointRow> get endpoints => _endpoints;
  String? get endpoint => _endpoint;
  String? get selectedModel => _selectedModel;
  String? get workspaceRoot => _workspaceRoot;
  AgentExecutionMode get executionMode => _executionMode;
  EffortLevel get effort => _effort;
  AgentToolProtocol get toolProtocol => _toolProtocol;
  int get maxSteps => _maxStepsOverride ?? _effort.maxSteps;
  int get maxTokens => _maxTokens;
  int get timeoutSeconds => _timeoutSeconds;
  bool get allowWrite => _allowWrite;
  bool get allowExec => _allowExec;
  bool get authorizing => _authorizing;
  bool get recoveryBlocked => _recoveryBlocked;
  String? get error => _error;
  String? get pendingRequestSha256 => _pendingRequestSha256;
  List<Map<String, dynamic>> get progress => _progress;
  OperationController get operationState => _operationState;
  OperationSnapshot? get snapshot => _operationState.execution;
  OperationResult? get terminalResult => _operationState.terminalResult;
  bool get active =>
      _authorizing ||
      _operationState.observerState == OperationObserverState.connecting ||
      _operationState.observerState == OperationObserverState.observing ||
      (snapshot != null && snapshot!.state.isTerminal == false);

  Future<void> loadEndpoints() async {
    try {
      final rows = await client.endpointRoster();
      _endpoints = List<EndpointRow>.unmodifiable(rows);
      _endpoint ??= rows.isNotEmpty ? rows.first.name : null;
      if (_executionMode.isNativeCli &&
          !agentExecutionModeSupportsEndpoint(_executionMode, _endpoint)) {
        _endpoint = _nativeCliEndpoint(rows);
        _selectedModel = null;
      }
      notifyListeners();
    } catch (error) {
      _error = '$error';
      notifyListeners();
    }
  }

  void setEndpoint(String? value) {
    if (_endpoint == value) return;
    _endpoint = value;
    _selectedModel = null;
    _bump();
  }

  void setExecutionMode(AgentExecutionMode value) {
    if (_executionMode == value) return;
    _executionMode = value;
    if (value.isNativeCli) {
      _toolProtocol = AgentToolProtocol.compatibility;
      _allowExec = false;
      if (!agentExecutionModeSupportsEndpoint(value, _endpoint)) {
        _endpoint = _nativeCliEndpoint(_endpoints);
        _selectedModel = null;
      }
    }
    _bump();
  }

  void setModel(String value) {
    final next = value.trim().isEmpty ? null : value.trim();
    if (next != null && !_modelId.hasMatch(next)) {
      _error = 'INVALID_MODEL';
      notifyListeners();
      return;
    }
    if (_selectedModel == next) return;
    _selectedModel = next;
    _bump();
  }

  void setWorkspaceRoot(String value) {
    final next = value.trim().isEmpty ? null : value.trim();
    if (_workspaceRoot == next) return;
    _workspaceRoot = next;
    _bump();
  }

  void setEffort(EffortLevel value) {
    if (_effort == value && _maxStepsOverride == null) return;
    _effort = value;
    _maxStepsOverride = null;
    _bump();
  }

  void setToolProtocol(AgentToolProtocol value) {
    if (_executionMode.isNativeCli &&
        value != AgentToolProtocol.compatibility) {
      return;
    }
    if (_toolProtocol == value) return;
    _toolProtocol = value;
    _bump();
  }

  String? _nativeCliEndpoint(List<EndpointRow> rows) {
    for (final row in rows) {
      if (row.name == 'claude-cli') return row.name;
    }
    return null;
  }

  void dismissRecoveryBlock() {
    if (!_recoveryBlocked) return;
    _recoveryBlocked = false;
    _pendingRequestSha256 = null;
    _error = null;
    _clearPersistedPendingRecovery();
    notifyListeners();
  }

  void _clearPersistedPendingRecovery() {
    final store = _sessionStore;
    if (store == null) return;
    try {
      final prior = store.load();
      if (prior == null || prior.operationRequestSha256 == null) return;
      store.save(
        JourneySession(
          journeyRef: prior.journeyRef,
          lens: prior.lens,
          selectionRef: prior.selectionRef,
          operationRef: prior.operationRef,
          operationEventHeadSha256: prior.operationEventHeadSha256,
          operationExecutionMode: prior.operationExecutionMode,
          detailsExpanded: prior.detailsExpanded,
          recoveryVisible: prior.recoveryVisible,
        ),
      );
    } on Object {
      // Session locators are hints; duplicate suppression remains in memory.
    }
  }

  void setMaxStepsOverride(int? value) {
    if (value != null && (value < 1 || value > 12)) {
      _error = 'INVALID_MAX_STEPS';
      notifyListeners();
      return;
    }
    if (_maxStepsOverride == value) return;
    _maxStepsOverride = value;
    _bump();
  }

  void setMaxTokens(int value) {
    if (value < 1 || value > 32768) {
      _error = 'INVALID_MAX_TOKENS';
      notifyListeners();
      return;
    }
    if (_maxTokens == value) return;
    _maxTokens = value;
    _bump();
  }

  void setTimeoutSeconds(int value) {
    if (value < 1 || value > 1800) {
      _error = 'INVALID_TIMEOUT';
      notifyListeners();
      return;
    }
    if (_timeoutSeconds == value) return;
    _timeoutSeconds = value;
    _bump();
  }

  void setAllowWrite(bool value) {
    if (_allowWrite == value) return;
    _allowWrite = value;
    _bump();
  }

  void setAllowExec(bool value) {
    if (_executionMode.isNativeCli && value) {
      if (_allowExec) {
        _allowExec = false;
        _bump();
      }
      return;
    }
    if (_allowExec == value) return;
    _allowExec = value;
    _bump();
  }

  void _bump() {
    _configGeneration++;
    _error = null;
    notifyListeners();
  }

  void _changed() => notifyListeners();

  @override
  void dispose() {
    _operationState.dispose();
    _stopGrants.dispose();
    super.dispose();
  }
}

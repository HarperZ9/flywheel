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
import '../models/rowan_mcp_catalog.dart';
import '../models/rowan_run_budget.dart';
import '../services/journey_session_store.dart';
import '../widgets/effort_dial.dart';
import '../widgets/operation_grant_sheet.dart';
import 'gateway_operation_controller.dart';
import 'operation_controller.dart';

part 'rowan_operation_controller_parts.dart';
part 'rowan_operation_controller_private.dart';
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
  Map<String, Object?>? _mcpAdmission;
  RowanMcpCatalog? _mcpCatalog;
  RowanMcpOption? _selectedMcpOption;
  AgentExecutionMode _executionMode = AgentExecutionMode.api;
  EffortLevel _effort = EffortLevel.standard;
  AgentToolProtocol _toolProtocol = AgentToolProtocol.compatibility;
  int _maxTokens = 1024, _timeoutSeconds = 300;
  int? _maxStepsOverride;
  RowanRunBudget _runBudget = const RowanRunBudget();
  String? _checkCommand;
  bool _allowWrite = false, _allowExec = false, _authorizing = false;
  bool _recovering = false;
  bool _mcpCatalogLoading = false, _mcpDiscoveryRunning = false;
  bool _recoveryBlocked = false;
  int _configGeneration = 0, _mcpAdmissionGeneration = 0;
  String? _pendingRequestSha256;
  Future<bool>? _recoveryFuture;
  List<Map<String, dynamic>> _progress = const [];

  List<EndpointRow> get endpoints => _endpoints;
  String? get endpoint => _endpoint;
  String? get selectedModel => _selectedModel;
  String? get workspaceRoot => _workspaceRoot;
  Map<String, Object?>? get mcpAdmission => _mcpAdmission;
  RowanMcpCatalog? get mcpCatalog => _mcpCatalog;
  List<RowanMcpOption> get mcpOptions => _mcpCatalog?.options ?? const [];
  RowanMcpOption? get selectedMcpOption => _selectedMcpOption;
  AgentExecutionMode get executionMode => _executionMode;
  EffortLevel get effort => _effort;
  AgentToolProtocol get toolProtocol => _toolProtocol;
  int get maxSteps => _maxStepsOverride ?? _effort.maxSteps;
  int get maxTokens => _maxTokens;
  int get timeoutSeconds => _timeoutSeconds;
  RowanRunBudget get runBudget => _runBudget;
  String? get checkCommand => _checkCommand;
  bool get allowWrite => _allowWrite;
  bool get allowExec => _allowExec;
  bool get authorizing => _authorizing;
  bool get mcpCatalogLoading => _mcpCatalogLoading;
  bool get mcpDiscoveryRunning => _mcpDiscoveryRunning;
  bool get recoveryBlocked => _recoveryBlocked;
  String? get error => _error;
  String? get pendingRequestSha256 => _pendingRequestSha256;
  List<Map<String, dynamic>> get progress => _progress;
  OperationController get operationState => _operationState;
  OperationSnapshot? get snapshot => _operationState.execution;
  OperationResult? get terminalResult => _operationState.terminalResult;
  bool get active =>
      _authorizing ||
      _recovering ||
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
      _selectedMcpOption = null;
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

  void setMcpAdmission(Map<String, Object?>? value) {
    final next = value == null ? null : _jsonObjectCopy(value);
    if (jsonEncode(_mcpAdmission) == jsonEncode(next)) return;
    if (next != null && _executionMode.isNativeCli) {
      _invalidateMcpAdmission();
      _error = 'AGENT_NATIVE_CLI_MCP_UNSUPPORTED';
      _changed();
      return;
    }
    _mcpAdmission = next;
    _mcpAdmissionGeneration++;
    _mcpDiscoveryRunning = false;
    _bump(invalidateMcpAdmission: false);
  }

  Future<void> loadMcpCatalog() async {
    if (_executionMode.isNativeCli) {
      _error = 'AGENT_NATIVE_CLI_MCP_UNSUPPORTED';
      _changed();
      return;
    }
    _mcpCatalogLoading = true;
    _error = null;
    _changed();
    try {
      final catalog = await client.agentMcpCatalog();
      final options = catalog.options;
      _invalidateMcpAdmission();
      _mcpCatalog = catalog;
      if (_selectedMcpOption == null ||
          !options.any((option) => option.key == _selectedMcpOption!.key)) {
        _selectedMcpOption = options.isEmpty ? null : options.first;
      }
    } on Object catch (error) {
      _invalidateMcpAdmission();
      _error = '$error';
    } finally {
      _mcpCatalogLoading = false;
      _changed();
    }
  }

  void selectMcpOption(String? key) {
    if (key == null) return;
    RowanMcpOption? match;
    for (final option in mcpOptions) {
      if (option.key == key) {
        match = option;
        break;
      }
    }
    if (match == null || _selectedMcpOption?.key == match.key) return;
    _selectedMcpOption = match;
    _bump();
  }

  Future<void> admitSelectedMcpTool() async {
    if (_executionMode.isNativeCli) {
      _error = 'AGENT_NATIVE_CLI_MCP_UNSUPPORTED';
      _changed();
      return;
    }
    final option =
        _selectedMcpOption ?? (mcpOptions.isEmpty ? null : mcpOptions.first);
    if (option == null) {
      _invalidateMcpAdmission();
      _error = 'AGENT_MCP_SELECTION_REQUIRED';
      _changed();
      return;
    }
    final admissionGeneration = _invalidateMcpAdmission();
    _mcpDiscoveryRunning = true;
    _error = null;
    _configGeneration++;
    _changed();
    try {
      final response = await client.discoverAgentMcp(option: option);
      if (admissionGeneration == _mcpAdmissionGeneration &&
          _selectedMcpOption?.key == option.key) {
        _mcpAdmission = _jsonObjectCopy(response.mcpAdmission);
        _toolProtocol = AgentToolProtocol.native;
        _bump(invalidateMcpAdmission: false);
      }
    } on Object catch (error) {
      if (admissionGeneration == _mcpAdmissionGeneration) {
        _mcpAdmission = null;
        _error = '$error';
        _changed();
      }
    } finally {
      if (admissionGeneration == _mcpAdmissionGeneration) {
        _mcpDiscoveryRunning = false;
        _changed();
      }
    }
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
    _clearPersistedRowanRecovery(_sessionStore);
    notifyListeners();
  }

  /// The owner's per-run limits. The engine fills unset ones with defaults.
  void setRunBudget(RowanRunBudget value) {
    if (value.invalidField != null) {
      _error = 'INVALID_RUN_BUDGET';
      notifyListeners();
      return;
    }
    if (_runBudget == value) return;
    _runBudget = value;
    _bump();
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

  void _bump({bool invalidateMcpAdmission = true}) {
    _configGeneration++;
    if (invalidateMcpAdmission) _invalidateMcpAdmission();
    _error = null;
    notifyListeners();
  }

  int _invalidateMcpAdmission() {
    _mcpAdmission = null;
    _mcpDiscoveryRunning = false;
    return ++_mcpAdmissionGeneration;
  }

  void _changed() => notifyListeners();

  @override
  void dispose() {
    _operationState.dispose();
    _stopGrants.dispose();
    super.dispose();
  }
}

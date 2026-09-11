import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/widgets.dart';

import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../models/evidence_state.dart';
import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../services/journey_session_store.dart';
import '../widgets/effort_dial.dart';
import '../widgets/operation_grant_sheet.dart';
import 'gateway_operation_controller.dart';
import 'operation_controller.dart';

part 'rowan_operation_controller_parts.dart';

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
  EffortLevel _effort = EffortLevel.standard;
  int _maxTokens = 1024, _timeoutSeconds = 300;
  int? _maxStepsOverride;
  bool _allowWrite = false, _allowExec = false, _authorizing = false;
  int _configGeneration = 0;
  String? _pendingRequestSha256;
  List<Map<String, dynamic>> _progress = const [];

  List<EndpointRow> get endpoints => _endpoints;
  String? get endpoint => _endpoint;
  String? get selectedModel => _selectedModel;
  String? get workspaceRoot => _workspaceRoot;
  EffortLevel get effort => _effort;
  int get maxSteps => _maxStepsOverride ?? _effort.maxSteps;
  int get maxTokens => _maxTokens;
  int get timeoutSeconds => _timeoutSeconds;
  bool get allowWrite => _allowWrite;
  bool get allowExec => _allowExec;
  bool get authorizing => _authorizing;
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

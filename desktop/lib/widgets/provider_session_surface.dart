import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/operation_controller.dart';
import '../controllers/provider_session_controller.dart';
import '../models/operation_models.dart';
import '../models/provider_session_models.dart';
import 'operation_grant_sheet.dart';
import 'provider_session_pane.dart';

part 'provider_session_surface_actions.dart';
part 'provider_session_surface_binding.dart';
part 'provider_session_surface_state_key.dart';

final class ProviderSessionSurface extends StatefulWidget {
  final GatewayClient client;
  final ProviderSessionController controller;
  final String provider, draft;
  final String? workspaceRef;
  final String? selectedModel;
  final ValueChanged<String> onProviderChanged, onDraftChanged;

  const ProviderSessionSurface({
    super.key,
    required this.client,
    required this.controller,
    required this.provider,
    required this.draft,
    required this.onProviderChanged,
    required this.onDraftChanged,
    this.workspaceRef,
    this.selectedModel,
  });

  @override
  State<ProviderSessionSurface> createState() => _ProviderSessionSurfaceState();
}

final class _ProviderSessionSurfaceState extends State<ProviderSessionSurface> {
  late final GatewayOperations _operations;
  late TextEditingController _draft;
  late GatewayOperationController _stopGrants;
  late GatewayOperationController _approvalGrants;
  late OperationController _operation;
  ProviderSessionBinding? _binding;
  _ProviderSessionBindingKey? _bindingKey;
  GatewayJourneyBinding? _dependencyJourneyBinding;
  ProviderSessionApproval? _pendingApproval;
  Timer? _approvalPoll;
  String? _bindingError, _runError, _approvalError;
  bool _loadingBinding = false, _authorizing = false;
  bool _didCaptureDependencies = false;
  int _bindingGeneration = 0;

  @override
  void initState() {
    super.initState();
    _operations = GatewayOperations(widget.client);
    _draft = TextEditingController(text: widget.draft);
    _approvalGrants =
        GatewayOperationController(GatewayGrantClient(widget.client));
    _newOperationController();
    _loadBinding();
  }

  @override
  void didUpdateWidget(ProviderSessionSurface oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.provider != widget.provider ||
        oldWidget.client != widget.client ||
        oldWidget.workspaceRef != widget.workspaceRef ||
        oldWidget.selectedModel != widget.selectedModel) {
      _loadBinding();
    }
    if (oldWidget.draft != widget.draft && _draft.text != widget.draft) {
      _draft.text = widget.draft;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final journey = _journeyBindingDependency;
    if (!_didCaptureDependencies) {
      _didCaptureDependencies = true;
      _dependencyJourneyBinding = journey;
      return;
    }
    if (journey != _dependencyJourneyBinding) {
      _dependencyJourneyBinding = journey;
      _loadBinding();
    }
  }

  @override
  void dispose() {
    _draft.dispose();
    _operation.dispose();
    _stopGrants.dispose();
    _approvalGrants.dispose();
    _approvalPoll?.cancel();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  void _update(VoidCallback fn) {
    if (mounted) setState(fn);
  }

  void _newOperationController() {
    _stopGrants = GatewayOperationController(GatewayGrantClient(widget.client));
    _operation = OperationController(
      requestId: () => 'native-stop-${DateTime.now().microsecondsSinceEpoch}',
      grants: _stopGrants,
      onTerminalResult: widget.controller.acceptTerminal,
    )..addListener(_changed);
  }

  void _resetOperationController() {
    _operation.removeListener(_changed);
    _operation.dispose();
    _stopGrants.dispose();
    _newOperationController();
  }

  @override
  Widget build(BuildContext context) => Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 8),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              DropdownButton<String>(
                value: widget.provider,
                items: [
                  for (final provider in providerSessionProviders)
                    DropdownMenuItem(value: provider, child: Text(provider)),
                ],
                onChanged: _authorizing
                    ? null
                    : (value) {
                        if (value != null) widget.onProviderChanged(value);
                      },
              ),
              const SizedBox(width: 16),
              Expanded(child: Text(_bindingStatus)),
            ]),
            Text('Model: ${_modelText ?? 'provider default'}'),
            Text('Workspace binding: ${widget.workspaceRef ?? 'none'}'),
            Text(_approvalStatus),
            if (_pendingApproval != null)
              Wrap(spacing: 8, children: [
                OutlinedButton(
                  onPressed: _authorizing ? null : _denyPendingApproval,
                  child: const Text('Deny provider request'),
                ),
                FilledButton(
                  onPressed: _authorizing ? null : _allowPendingApproval,
                  child: const Text('Allow provider request'),
                ),
              ]),
            if (_runError != null) Text('Run status: $_runError'),
            if (_approvalError != null)
              Text('Provider approval status: $_approvalError'),
            TextField(
              controller: _draft,
              decoration: const InputDecoration(
                labelText: 'Native session message',
              ),
              minLines: 2,
              maxLines: 4,
              onChanged: widget.onDraftChanged,
            ),
          ]),
        ),
        Expanded(
          child: ProviderSessionPane(
            controller: widget.controller,
            onSendTurn: _canSend ? _sendTurn : null,
            onStop: _canStop ? _stop : null,
            onResume: _canResume ? _resume : null,
            onReconcile: _canReconcile ? _reconcile : null,
          ),
        ),
      ]);

  bool get _canSend =>
      _binding != null &&
      _bindingIsCurrent(_binding!) &&
      _binding!.admitted &&
      !_authorizing &&
      widget.draft.trim().isNotEmpty &&
      widget.controller.state.canSendTurn;
  bool get _canStop =>
      _operation.execution?.state == OperationState.running &&
      _operation.execution?.canCancel == true;
  bool get _canResume =>
      _binding != null &&
      _bindingIsCurrent(_binding!) &&
      _binding!.admitted &&
      !_authorizing &&
      widget.controller.state.operationRef.isNotEmpty;
  bool get _canReconcile =>
      _canResume && widget.controller.state.needsReconcile;
  String? get _modelText =>
      widget.selectedModel == null || widget.selectedModel!.trim().isEmpty
          ? null
          : widget.selectedModel!.trim();
  String get _bindingStatus {
    if (_loadingBinding) return 'Loading provider binding...';
    final binding = _binding;
    if (binding == null) {
      return 'Binding unavailable: ${_bindingError ?? 'not loaded'}';
    }
    if (!binding.admitted) {
      return 'Binding disabled: ${binding.reason}';
    }
    final capability = binding.capabilityDigest.isEmpty
        ? 'capability not reported'
        : 'capability ${binding.capabilityDigest.substring(0, 12)}';
    return '${binding.workspaceRef} · config '
        '${_short(binding.configDigest)} · binding '
        '${binding.providerBindingRef.substring(0, 12)} · $capability';
  }

  String get _approvalStatus {
    final approval = _pendingApproval;
    if (approval == null) {
      return 'Live provider approvals: none pending';
    }
    return 'Live provider approval pending: ${approval.tool} '
        '${approval.payloadSha256.substring(0, 12)}';
  }
}

String _short(String value) =>
    value.length <= 12 ? value : value.substring(0, 12);

import 'dart:async';
import 'package:flutter/material.dart';
import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/operation_controller.dart';
import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/operation_grant_sheet.dart';
import '../widgets/operation_controls.dart';
import 'agent_gates.dart';
import 'agent_runs_panel.dart';
import 'editor_pane.dart';
import 'live_run_tail.dart';

class AgentPanel extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final String workspaceRoot;
  final String? activeFile, selection;
  final EditorAttachmentSupplier? currentAttachment;
  final VoidCallback onRunStarted, onRunFinished;
  final TextEditingController? goalController;
  const AgentPanel(
      {super.key,
      required this.client,
      required this.alive,
      required this.workspaceRoot,
      required this.onRunStarted,
      required this.onRunFinished,
      this.activeFile,
      this.selection,
      this.currentAttachment,
      this.goalController});
  @override
  State<AgentPanel> createState() => _AgentPanelState();
}

class _AgentPanelState extends State<AgentPanel> {
  late final TextEditingController _goal =
      widget.goalController ?? TextEditingController();
  final _scroll = ScrollController();
  List<EndpointRow> _endpoints = [];
  String? _endpoint, _error;
  bool _allowWrite = false, _allowExec = false, _attachContext = true;
  bool _authorizing = false, _started = false, _pastOpen = false;
  List<Map<String, dynamic>> _events = [], _pastRuns = [];
  late final GatewayOperations _operations;
  late final GatewayOperationController _stopGrants;
  late OperationController _operationState;
  Map<String, dynamic>? _stored;
  @override
  void initState() {
    super.initState();
    _operations = GatewayOperations(widget.client);
    _stopGrants = GatewayOperationController(GatewayGrantClient(widget.client));
    _operationState = _newOperationState();
    _loadEndpoints();
  }

  @override
  void dispose() {
    _operationState.dispose();
    _stopGrants.dispose();
    _scroll.dispose();
    if (widget.goalController == null) _goal.dispose();
    super.dispose();
  }

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (mounted) {
        setState(() {
          _endpoints = rows;
          _endpoint ??= rows.isNotEmpty ? rows.first.name : null;
        });
      }
    } catch (_) {}
  }

  OperationController _newOperationState() => OperationController(
      requestId: () => 'desktop-stop-${DateTime.now().microsecondsSinceEpoch}',
      grants: _stopGrants,
      onTerminalResult: _finished)
    ..addListener(_stateChanged);
  void _beginRun() {
    _operationState.dispose();
    _operationState = _newOperationState();
    widget.onRunStarted();
    setState(() {
      _authorizing = false;
      _started = true;
      _events = [];
      _stored = _error = null;
    });
  }

  GatewayOperation? _operation(String request) {
    final endpoint = _endpoint, input = _goal.text.trim();
    if (endpoint == null || input.isEmpty) return null;
    try {
      final attachment = closedEditorAttachment(_attachContext,
          widget.currentAttachment, widget.activeFile, widget.selection);
      return GatewayOperation.exact(
          action: 'agent.run',
          clientRequestId: request,
          operation: {
            'goal': input,
            'endpoint': endpoint,
            'max_steps': 10,
            'allow_write': _allowWrite,
            'allow_exec': _allowExec,
            'stream': true,
            if (attachment != null) 'attachment': attachment,
            'root': widget.workspaceRoot
          });
    } catch (_) {
      return null;
    }
  }

  Future<void> _run() async {
    if (_authorizing || _started) return;
    final request = 'desktop-agent-${DateTime.now().microsecondsSinceEpoch}';
    final operation = _operation(request);
    if (operation == null) {
      setState(() => _error = 'INVALID_CONTEXT');
      return;
    }
    setState(() => _authorizing = true);
    await authorizeGatewayStream(context, operation, (body) {
      if (!mounted) return;
      _beginRun();
      _operationState.observe(_operations.start(body),
          onProgress: _onProgress, onInterrupted: _interrupted);
    }, () {
      if (!mounted) return;
      setState(() => _authorizing = false);
    }, currentOperation: () => _operation(request));
  }

  void _onProgress(Map<String, dynamic> event) {
    if (!mounted) return;
    setState(() => _events = [..._events, event]);
    _scrollTail();
  }

  void _interrupted() => setState(() => _error = 'INVALID_RESPONSE');

  void _stateChanged() => setState(() {});

  void _finished(OperationResult result) {
    setState(() {
      _events = [
        ..._events,
        {...result.result, 'type': 'done'}
      ];
      _started = false;
    });
    widget.onRunFinished();
    if (_pastOpen) _loadPastRuns();
  }

  Future<void> _stop() async {
    final operation = _operationState.stopOperation();
    if (operation == null || !await _operationState.prepareStop(operation)) {
      if (mounted && _stopGrants.failure != null) {
        setState(() => _error = _stopGrants.failure!.code);
      }
      return;
    }
    if (!mounted) return;
    await showOperationGrantSheet<OperationSnapshot>(context, _stopGrants,
        (body) async {
      final snapshot = await _operations.cancel(body);
      if (!_operationState.acceptCancelResponse(snapshot)) {
        throw StateError('invalid operation response');
      }
      return snapshot;
    });
  }

  void _scrollTail() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.jumpTo(_scroll.position.maxScrollExtent);
        }
      });
  Future<void> _loadPastRuns() async {
    try {
      final r = await widget.client.agentRuns(limit: 10);
      if (mounted) {
        setState(() => _pastRuns = ((r['runs'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .toList());
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _openStored(Map<String, dynamic> row) async {
    try {
      final doc = await widget.client.agentRunDetail('${row['run_id'] ?? ''}');
      if (mounted) setState(() => _stored = doc);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(top: BorderSide(color: t.line)),
      ),
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _header(t),
          const SizedBox(height: FwLayout.s2),
          if (_pastOpen)
            _pastSection()
          else ...[
            AgentOperationComposer(
                controller: _goal,
                alive: widget.alive,
                authorizing: _authorizing,
                snapshot: _operationState.execution,
                onRun: () => unawaited(_run()),
                onStop: () => unawaited(_stop())),
            const SizedBox(height: FwLayout.s2),
            AgentGates(
              endpoints: _endpoints,
              endpoint: _endpoint,
              allowWrite: _allowWrite,
              allowExec: _allowExec,
              attachContext: _attachContext,
              onEndpoint: (v) => setState(() => _endpoint = v),
              onWrite: (v) => setState(() => _allowWrite = v),
              onExec: (v) => setState(() => _allowExec = v),
              onAttach: (v) => setState(() => _attachContext = v),
            ),
            if (_error != null) ...[
              const SizedBox(height: FwLayout.s2),
              HonestNull('The run failed: $_error'),
            ],
            if (_events.isNotEmpty) ...[
              const SizedBox(height: FwLayout.s2),
              LiveRunTail(
                  events: _events, scroll: _scroll, client: widget.client),
            ],
          ],
        ],
      ),
    );
  }

  Widget _header(FwTokens t) => Row(
        children: [
          Kicker('workspace agent', hot: !_pastOpen),
          const Spacer(),
          if (!widget.alive)
            Text('engine offline', style: fwMono(t, size: 10.5, color: t.drift))
          else
            TextButton(
              onPressed: () {
                setState(() {
                  _pastOpen = !_pastOpen;
                  _stored = null;
                });
                if (_pastOpen) _loadPastRuns();
              },
              child: Text(_pastOpen ? 'live' : 'past runs',
                  style: fwMono(t, size: 11, color: t.inkMuted)),
            ),
        ],
      );
  Widget _pastSection() => ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 280),
        child: SingleChildScrollView(
          child: _stored != null
              ? StoredAgentRun(doc: _stored!, client: widget.client)
              : AgentRunsList(runs: _pastRuns, onOpen: _openStored),
        ),
      );
}

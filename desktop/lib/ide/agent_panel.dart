import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/operation_grant_sheet.dart';
import 'agent_gates.dart';
import 'agent_runs_panel.dart';
import 'live_run_tail.dart';

class AgentPanel extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final String workspaceRoot;
  final String? activeFile;
  final String? selection;
  final VoidCallback onRunStarted;
  final VoidCallback onRunFinished;

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
      this.goalController});

  @override
  State<AgentPanel> createState() => _AgentPanelState();
}

class _AgentPanelState extends State<AgentPanel> {
  late final TextEditingController _goal =
      widget.goalController ?? TextEditingController();
  final _scroll = ScrollController();
  List<EndpointRow> _endpoints = [];
  String? _endpoint;
  bool _allowWrite = true, _allowExec = false, _attachContext = true;
  bool _running = false, _detached = false, _pastOpen = false;
  List<Map<String, dynamic>> _events = [];
  StreamSubscription<Map<String, dynamic>>? _sub;
  List<Map<String, dynamic>> _pastRuns = [];
  Map<String, dynamic>? _stored;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadEndpoints();
  }

  @override
  void dispose() {
    _sub?.cancel();
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

  Future<void> _run() async {
    var goal = _goal.text.trim();
    if (goal.isEmpty || _endpoint == null || _running) return;
    if (_attachContext && widget.activeFile != null) {
      final sel = widget.selection;
      goal = 'Active file: ${widget.activeFile}\n'
          '${sel != null && sel.isNotEmpty ? 'Selected text:\n$sel\n' : ''}'
          '\n$goal';
    }
    widget.onRunStarted();
    setState(() {
      _running = true;
      _detached = false;
      _events = [];
      _stored = null;
      _error = null;
    });
    final operation = GatewayOperation.exact(
        action: 'agent.run',
        clientRequestId:
            'desktop-agent-${DateTime.now().microsecondsSinceEpoch}',
        operation: {
          'goal': goal,
          'endpoint': _endpoint!,
          'max_steps': 10,
          'allow_write': _allowWrite,
          'allow_exec': _allowExec,
          'stream': true,
          'root': widget.workspaceRoot
        });
    await authorizeGatewayStream(context, operation, (body) {
      _sub = widget.client
          .agentStream(goal, _endpoint!,
              maxSteps: 10,
              allowWrite: _allowWrite,
              allowExec: _allowExec,
              root: widget.workspaceRoot,
              authorizedBody: body)
          .listen(_onEvent, onError: (e) {
        if (mounted) {
          setState(() {
            _error = '$e';
            _running = false;
          });
        }
        widget.onRunFinished();
      }, onDone: () {
        if (mounted) setState(() => _running = false);
      });
    }, () {
      if (!mounted) return;
      setState(() => _running = false);
      widget.onRunFinished();
    });
  }

  void _onEvent(Map<String, dynamic> e) {
    if (!mounted) return;
    setState(() => _events = [..._events, e]);
    if (e['type'] == 'done') {
      widget.onRunFinished();
      if (_pastOpen) _loadPastRuns();
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final end = _scroll.position.maxScrollExtent;
      if (MediaQuery.of(context).disableAnimations) {
        _scroll.jumpTo(end);
      } else {
        _scroll.animateTo(end,
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutQuart);
      }
    });
  }

  void _detach() {
    _sub?.cancel();
    setState(() {
      _running = false;
      _detached = true;
    });
    widget.onRunFinished();
  }

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
            _composerRow(),
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
            if (_detached) ...[
              const SizedBox(height: FwLayout.s2),
              const HonestNull(
                  'Detached. The gated run continues in the engine and lands '
                  'under past runs with its full trace.'),
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

  Widget _pastSection() {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 280),
      child: SingleChildScrollView(
        child: _stored != null
            ? StoredAgentRun(doc: _stored!, client: widget.client)
            : AgentRunsList(runs: _pastRuns, onOpen: _openStored),
      ),
    );
  }

  Widget _composerRow() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextField(
            controller: _goal,
            maxLines: 2,
            minLines: 1,
            enabled: widget.alive,
            style: const TextStyle(fontSize: 13),
            decoration:
                const InputDecoration(hintText: 'Change this workspace…'),
            onSubmitted: (_) => unawaited(_run()),
          ),
        ),
        const SizedBox(width: FwLayout.s2),
        if (_running) ...[
          OutlinedButton(onPressed: _detach, child: const Text('Detach')),
          const SizedBox(width: FwLayout.s2),
        ],
        FilledButton(
          onPressed: widget.alive && !_running ? () => unawaited(_run()) : null,
          child: Text(_running ? 'Running…' : 'Run'),
        ),
      ],
    );
  }
}

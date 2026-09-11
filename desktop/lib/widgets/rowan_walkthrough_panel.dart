import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../controllers/operation_controller.dart';
import '../controllers/rowan_walkthrough_controller.dart';
import '../ide/live_run_tail.dart';
import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../models/rowan_walkthrough_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'model_selector.dart';
import 'operation_controls.dart';
import 'operation_grant_sheet.dart';

part 'rowan_walkthrough_panel_parts.dart';

class RowanWalkthroughPanel extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final JourneyController? journey;
  final GatewayJourneyBinding? currentBinding;
  final RowanWalkthroughController? controller;
  final RowanWalkthroughCaptionBuilder? captionBuilder;
  final RowanWalkthroughFollowUpReviewer? onReviewFollowUp;

  const RowanWalkthroughPanel({
    super.key,
    required this.client,
    required this.alive,
    this.journey,
    this.currentBinding,
    this.controller,
    this.captionBuilder,
    this.onReviewFollowUp,
  });

  @override
  State<RowanWalkthroughPanel> createState() => _RowanWalkthroughPanelState();
}

class _RowanWalkthroughPanelState extends State<RowanWalkthroughPanel> {
  late final RowanWalkthroughController _controller = widget.controller ??
      RowanWalkthroughController(scenario: rowanRetryPolicyWalkthroughScenario);
  late final bool _ownsController = widget.controller == null;
  late final GatewayOperations _operations = GatewayOperations(widget.client);
  late final GatewayOperationController _stopGrants =
      GatewayOperationController(GatewayGrantClient(widget.client));
  late OperationController _operationState = _newOperationState();
  final _root = TextEditingController();
  final _scroll = ScrollController();
  List<EndpointRow> _endpoints = const [];
  bool _authorizing = false, _guidancePaused = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _root.text = _controller.root ?? '';
    _controller.addListener(_changed);
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(RowanWalkthroughPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.alive && widget.alive) _loadEndpoints();
  }

  @override
  void dispose() {
    _controller.removeListener(_changed);
    if (_ownsController) _controller.dispose();
    _operationState.dispose();
    _stopGrants.dispose();
    _root.dispose();
    _scroll.dispose();
    super.dispose();
  }

  OperationController _newOperationState() => OperationController(
        requestId: () => 'rowan-stop-${DateTime.now().microsecondsSinceEpoch}',
        grants: _stopGrants,
        onTerminalResult: _controller.acceptTerminalResult,
      )..addListener(_operationChanged);

  GatewayJourneyBinding? get _binding {
    if (widget.currentBinding != null) return widget.currentBinding;
    final projection = widget.journey?.state.projection;
    if (projection == null ||
        widget.journey?.state.activeJourneyRef != projection.journeyRef) {
      return null;
    }
    return GatewayJourneyBinding(
      projection.journeyRef,
      projection.eventHeadSha256,
    );
  }

  bool get _canRun => widget.alive && _controller.ready && _binding != null;

  void _changed() {
    if (mounted) setState(() {});
  }

  void _operationChanged() {
    final snapshot = _operationState.execution;
    if (snapshot != null && snapshot != _controller.snapshot) {
      _controller.acceptSnapshot(snapshot);
    }
    if (mounted) setState(() {});
  }

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (!mounted) return;
      setState(() => _endpoints = rows);
      _controller.selectEndpoint(defaultEndpoint(rows)?.name);
    } catch (error) {
      if (mounted) setState(() => _error = 'Endpoint roster unavailable.');
    }
  }

  Future<void> _run() async {
    if (_authorizing || _operationState.execution?.isTerminal == false) return;
    final request =
        'rowan-walkthrough-${DateTime.now().microsecondsSinceEpoch}';
    final binding = _binding;
    final operation = _controller.operationFor(request);
    if (binding == null || operation == null) {
      setState(() => _error = 'Select endpoint, model, root, and Journey.');
      return;
    }
    _controller.markReviewPrepared();
    setState(() {
      _authorizing = true;
      _error = null;
    });
    await authorizeGatewayStream(
      context,
      operation,
      (body) {
        if (!mounted) return;
        _operationState.dispose();
        _operationState = _newOperationState();
        _controller.beginExecution();
        setState(() => _authorizing = false);
        _operationState.observe(
          _operations.start(body),
          onProgress: _progress,
          onInterrupted: _interrupted,
        );
      },
      () {
        if (!mounted) return;
        setState(() => _authorizing = false);
        _controller.markDenied();
      },
      currentOperation: () =>
          _binding == binding ? _controller.operationFor(request) : null,
    );
  }

  void _progress(Map<String, dynamic> event) {
    _controller.acceptProgress(event);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  void _interrupted() {
    _controller.markInterrupted();
    if (mounted) setState(() => _error = 'Run interrupted or invalid.');
  }

  Future<void> _stop() async {
    final operation = _operationState.stopOperation();
    if (operation == null || !await _operationState.prepareStop(operation)) {
      setState(() => _error = 'Stop approval unavailable.');
      return;
    }
    if (!mounted) return;
    await showOperationGrantSheet<OperationSnapshot>(
      context,
      _stopGrants,
      (body) => _operations.cancel(body),
    );
  }

  Future<void> _reopen() async {
    final terminal = _operationState.terminalResult;
    if (terminal == null) return;
    try {
      final snapshot = await _operations.snapshot(terminal.operationRef);
      _controller.markReopened(snapshot);
    } catch (_) {
      _controller.markInterrupted();
      setState(() => _error = 'Stored operation record unavailable.');
    }
  }

  Future<void> _reviewFollowUp() async {
    final result = _controller.terminalResult;
    final snapshot = _controller.snapshot;
    if (!_controller.canPrepareFollowUp ||
        result == null ||
        snapshot == null ||
        widget.onReviewFollowUp == null) {
      return;
    }
    await widget.onReviewFollowUp!(snapshot, result);
  }

  @override
  Widget build(BuildContext context) {
    final binding = _binding;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(
            child: SectionHeader(
              'Rowan live walkthrough',
              kicker: 'supervised native demo',
            ),
          ),
          OperationControls(
            alive: _canRun,
            authorizing: _authorizing,
            snapshot: _operationState.execution,
            onRun: _run,
            onStop: _stop,
          ),
        ]),
        const SizedBox(height: FwLayout.s3),
        Text(_controller.scenario.goal, style: const TextStyle(height: 1.45)),
        const SizedBox(height: FwLayout.s3),
        _RowanWalkthroughSelectors(
          client: widget.client,
          controller: _controller,
          endpoints: _endpoints,
          binding: binding,
          alive: widget.alive,
          root: _root,
        ),
        const SizedBox(height: FwLayout.s3),
        _RowanWalkthroughChips(controller: _controller),
        if (binding == null) ...[
          const SizedBox(height: FwLayout.s3),
          const HonestNull('Select a Journey before approval. The walkthrough '
              'will not dispatch without a current Journey head.'),
        ],
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        const SizedBox(height: FwLayout.s3),
        _RowanGuidanceControl(
          paused: _guidancePaused,
          onToggle: () => setState(() => _guidancePaused = !_guidancePaused),
        ),
        const SizedBox(height: FwLayout.s3),
        Kicker('live trace', hot: !_guidancePaused),
        const SizedBox(height: FwLayout.s2),
        LiveRunTail(
          events: _controller.events,
          scroll: _scroll,
          client: widget.client,
        ),
        const SizedBox(height: FwLayout.s3),
        _RowanCaptionSlot(
          builder: widget.captionBuilder,
          controller: _controller,
        ),
        const SizedBox(height: FwLayout.s3),
        _RowanTerminalActions(
          controller: _controller,
          followUpAvailable: widget.onReviewFollowUp != null,
          onReopen: _reopen,
          onReviewFollowUp: _reviewFollowUp,
        ),
      ]),
    );
  }
}

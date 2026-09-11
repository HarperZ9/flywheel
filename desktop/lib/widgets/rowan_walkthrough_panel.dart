import 'package:flutter/material.dart';

import '../controllers/journey_controller.dart';
import '../controllers/rowan_walkthrough_controller.dart';
import '../controllers/rowan_walkthrough_operation_host.dart';
import '../ide/live_run_tail.dart';
import '../models/gateway_grant_models.dart';
import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../models/rowan_walkthrough_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'model_selector.dart';
import 'operation_controls.dart';

part 'rowan_walkthrough_panel_parts.dart';

class RowanWalkthroughPanel extends StatefulWidget {
  final bool alive;
  final RowanWalkthroughOperationHost operationHost;
  final JourneyController? journey;
  final GatewayJourneyBinding? currentBinding;
  final RowanWalkthroughController? controller;
  final RowanWalkthroughCaptionBuilder? captionBuilder;
  final RowanWalkthroughFollowUpReviewer? onReviewFollowUp;

  const RowanWalkthroughPanel({
    super.key,
    required this.alive,
    required this.operationHost,
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
  final _root = TextEditingController();
  final _scroll = ScrollController();
  bool _guidancePaused = false;
  int _observedProgressLength = 0;
  String? _observedTerminalSha256;
  String? _localError;

  RowanWalkthroughOperationHost get _host => widget.operationHost;

  @override
  void initState() {
    super.initState();
    _root.text = _host.workspaceRoot ?? '';
    _controller.addListener(_changed);
    _host.addListener(_hostChanged);
    _hydrateHost();
  }

  @override
  void didUpdateWidget(RowanWalkthroughPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.operationHost != widget.operationHost) {
      oldWidget.operationHost.removeListener(_hostChanged);
      _host.addListener(_hostChanged);
      _root.text = _host.workspaceRoot ?? '';
      _observedProgressLength = _host.progress.length;
      _observedTerminalSha256 = null;
      _acceptHostTerminal();
    }
    if (!oldWidget.alive && widget.alive) _hydrateHost();
  }

  @override
  void dispose() {
    _controller.removeListener(_changed);
    _host.removeListener(_hostChanged);
    if (_ownsController) _controller.dispose();
    _root.dispose();
    _scroll.dispose();
    super.dispose();
  }

  GatewayJourneyBinding? get _binding {
    if (widget.currentBinding != null) return widget.currentBinding;
    final projection = widget.journey?.state.projection;
    if (projection == null ||
        projection.invalidResponse ||
        widget.journey?.state.activeJourneyRef != projection.journeyRef) {
      return null;
    }
    return GatewayJourneyBinding(
      projection.journeyRef,
      projection.eventHeadSha256,
    );
  }

  bool get _ready {
    final endpoint = _host.endpoint;
    final model = _host.selectedModel;
    final root = _host.workspaceRoot;
    return widget.alive &&
        endpoint != null &&
        endpoint.isNotEmpty &&
        model != null &&
        model.isNotEmpty &&
        root != null &&
        root.trim().isNotEmpty &&
        _binding != null;
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  void _hostChanged() {
    final root = _host.workspaceRoot ?? '';
    if (_root.text != root) _root.text = root;
    if (_host.progress.length != _observedProgressLength) {
      _observedProgressLength = _host.progress.length;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.jumpTo(_scroll.position.maxScrollExtent);
        }
      });
    }
    _acceptHostTerminal();
    if (mounted) setState(() {});
  }

  Future<void> _hydrateHost() async {
    if (!widget.alive) return;
    try {
      await _host.loadEndpoints();
      if (_host.endpoint == null) {
        final fallback = defaultEndpoint(_host.endpoints);
        if (fallback != null) _host.setEndpoint(fallback.name);
      }
      await _host.recoverFromSession();
    } catch (_) {
      if (mounted) setState(() => _localError = 'Operation host unavailable.');
    }
  }

  void _acceptHostTerminal() {
    final result = _host.terminalResult;
    if (result == null) return;
    final hash = result.canonicalSha256;
    if (_observedTerminalSha256 == hash) return;
    _observedTerminalSha256 = hash;
    _controller.acceptTerminalResult(result, snapshot: _host.snapshot);
  }

  Future<void> _run() async {
    if (_host.authorizing || _host.active) return;
    if (!_ready) {
      setState(() => _localError =
          'Select endpoint, exact model, input root, and Journey.');
      return;
    }
    _controller.markReviewPrepared();
    _host.configureScenario(_controller.scenario);
    setState(() => _localError = null);
    final outcome = await _host.start(context, _controller.scenario.goal);
    if (!mounted) return;
    if (outcome.value == true) {
      _controller.beginExecution();
      _observedTerminalSha256 = null;
      _acceptHostTerminal();
      return;
    }
    if (outcome.failure != null) {
      setState(() => _localError = outcome.failure!.message);
    }
    _controller.markDenied();
  }

  Future<void> _stop() async {
    try {
      await _host.stop(context);
    } catch (_) {
      if (mounted) setState(() => _localError = 'Stop approval unavailable.');
    }
  }

  Future<void> _reopen() async {
    final snapshot = _host.snapshot;
    if (snapshot == null || _host.terminalResult == null) {
      _controller.markMissingRecord();
      setState(() => _localError = 'Stored operation record unavailable.');
      return;
    }
    try {
      await _host.reconnect(snapshot);
      _controller.markReopened(_host.snapshot ?? snapshot);
    } catch (_) {
      _controller.markInterrupted();
      setState(() => _localError = 'Stored operation record unavailable.');
    }
  }

  Future<void> _reviewFollowUp() async {
    final result = _host.terminalResult;
    final snapshot = _host.snapshot;
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
    final error = _localError ?? _host.error;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(
            child: SectionHeader(
              'Rowan live walkthrough',
              kicker: 'shared native operation',
            ),
          ),
          OperationControls(
            alive: _ready,
            authorizing: _host.authorizing,
            snapshot: _host.snapshot,
            onRun: _run,
            onStop: _stop,
          ),
        ]),
        const SizedBox(height: FwLayout.s3),
        Text(_controller.scenario.goal, style: const TextStyle(height: 1.45)),
        const SizedBox(height: FwLayout.s3),
        _RowanWalkthroughSelectors(
          host: _host,
          binding: binding,
          alive: widget.alive,
          root: _root,
        ),
        const SizedBox(height: FwLayout.s3),
        _RowanWalkthroughChips(controller: _controller, host: _host),
        if (binding == null) ...[
          const SizedBox(height: FwLayout.s3),
          const HonestNull('Select a Journey before approval. The walkthrough '
              'will not ask the shared controller to start without one.'),
        ],
        if (error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(error),
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
            events: _host.progress, scroll: _scroll, client: _host.client),
        const SizedBox(height: FwLayout.s3),
        _RowanCaptionSlot(
          builder: widget.captionBuilder,
          controller: _controller,
          host: _host,
        ),
        const SizedBox(height: FwLayout.s3),
        _RowanTerminalActions(
          controller: _controller,
          followUpAvailable: widget.onReviewFollowUp != null,
          onReopen: _host.terminalResult == null ? null : _reopen,
          onReviewFollowUp: _reviewFollowUp,
        ),
      ]),
    );
  }
}

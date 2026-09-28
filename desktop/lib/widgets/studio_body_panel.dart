import 'dart:async';
import 'package:flutter/material.dart';
import '../assistant/rowan_action_cue_event_binding.dart';
import '../client/gateway_client.dart';
import '../client/studio_body_client.dart';
import '../controllers/live_screen_sharing.dart';
import '../controllers/rowan_walkthrough_operation_host.dart';
import '../controllers/studio_body_controller.dart';
import '../models/studio_body_models.dart';
import 'fw.dart';
import 'studio_body_evidence.dart';
import 'studio_body_output.dart';

class StudioBodyPanel extends StatefulWidget {
  final GatewayClient? client;
  final StudioBodyController? controller;
  final LiveScreenSharing? liveScreenSharing;
  final RowanWalkthroughOperationHost? rowanHost;
  final RowanActionCueDispatch? rowanCueDispatch;
  const StudioBodyPanel(
      {super.key,
      this.client,
      this.controller,
      this.liveScreenSharing,
      this.rowanHost,
      this.rowanCueDispatch})
      : assert(client != null || controller != null);
  @override
  State<StudioBodyPanel> createState() => _StudioBodyPanelState();
}

class _StudioBodyPanelState extends State<StudioBodyPanel> {
  late StudioBodyController _controller;
  late bool _ownsController;
  Timer? _freshness;
  @override
  void initState() {
    super.initState();
    _attach();
    _freshness =
        Timer.periodic(const Duration(seconds: 1), (_) => _syncBinding());
  }

  void _attach() {
    _ownsController = widget.controller == null;
    _controller = widget.controller ??
        StudioBodyController(GatewayStudioBodyClient(widget.client!),
            dispatchCue: widget.rowanCueDispatch);
    widget.liveScreenSharing?.addListener(_syncBinding);
    widget.rowanHost?.addListener(_syncBinding);
    _syncBinding();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _controller.refreshStatus();
    });
  }

  @override
  void didUpdateWidget(covariant StudioBodyPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    oldWidget.liveScreenSharing?.removeListener(_syncBinding);
    oldWidget.rowanHost?.removeListener(_syncBinding);
    if (oldWidget.controller != widget.controller ||
        oldWidget.client != widget.client ||
        oldWidget.rowanCueDispatch != widget.rowanCueDispatch) {
      if (_ownsController) _controller.dispose();
      _attach();
    } else {
      widget.liveScreenSharing?.addListener(_syncBinding);
      widget.rowanHost?.addListener(_syncBinding);
      _syncBinding();
    }
  }

  @override
  void dispose() {
    _freshness?.cancel();
    widget.liveScreenSharing?.removeListener(_syncBinding);
    widget.rowanHost?.removeListener(_syncBinding);
    if (_ownsController) _controller.dispose();
    super.dispose();
  }

  void _syncBinding() {
    if (widget.controller != null && widget.liveScreenSharing == null) return;
    _controller.updateBinding(StudioBodyBinding.fromLiveScreen(
        widget.liveScreenSharing,
        rowanHost: widget.rowanHost));
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: _controller, builder: (context, _) => _body(context));

  Widget _body(BuildContext context) {
    final c = _controller;
    final sound = c.instrument == StudioBodyInstrument.sound;
    return HairlineCard(
        child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('Studio instruments'),
        const SizedBox(height: FwLayout.s2),
        Text('Create with sight and sound',
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: FwLayout.s2),
        const Text(
            'Use the screen delivered to Rowan as context for an instrument '
            'action. Inspect the image or listen to the sound, then trace the result.'),
        const SizedBox(height: FwLayout.s3),
        if (!c.binding.canSubmitStep) HonestNull(c.binding.blocker),
        if (c.status != null && !c.status!.authority.configured)
          const HonestNull(
              'Instrument authority is not configured. An authorized '
              'gateway grant is needed before this instrument can run.'),
        if (c.error != null) HonestNull(c.error!),
        Wrap(spacing: FwLayout.s2, children: [
          for (final item in StudioBodyInstrument.values)
            ChoiceChip(
              key: ValueKey('studio-body-instrument-${item.name}'),
              label:
                  Text(item == StudioBodyInstrument.sound ? 'Sound' : 'Visual'),
              selected: c.instrument == item,
              onSelected: c.busy ? null : (_) => c.setInstrument(item),
            ),
        ]),
        const SizedBox(height: FwLayout.s2),
        SizedBox(
            width: 220,
            child: TextFormField(
              initialValue: c.seed.toString(),
              enabled: !c.busy,
              decoration: const InputDecoration(labelText: 'Seed'),
              keyboardType: TextInputType.number,
              onChanged: c.setSeedText,
            )),
        if (sound) ...[
          Text('Duration: ${c.durationSeconds.round()} seconds'),
          Slider(
              value: c.durationSeconds,
              min: 6,
              max: 90,
              divisions: 84,
              label: '${c.durationSeconds.round()} seconds',
              onChanged: c.busy ? null : c.setDuration),
          Text('Root note: ${c.rootHz.round()} Hz'),
          Slider(
              value: c.rootHz,
              min: 55,
              max: 880,
              label: '${c.rootHz.round()} Hz',
              onChanged: c.busy ? null : c.setRoot),
        ],
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          OutlinedButton(
              key: const ValueKey('studio-body-refresh-status'),
              onPressed: c.busy ? null : c.refreshStatus,
              child: Text(c.busyStatus ? 'Checking…' : 'Check readiness')),
          OutlinedButton(
              key: const ValueKey('studio-body-refresh-observation'),
              onPressed: c.busy || !c.binding.canReadSnapshot
                  ? null
                  : () {
                      _syncBinding();
                      c.refreshSnapshot();
                    },
              child: Text(
                  c.busySnapshot ? 'Reading…' : 'Read current observation')),
          FilledButton(
              key: const ValueKey('studio-body-submit-step'),
              onPressed: !c.canSubmitStep
                  ? null
                  : () {
                      _syncBinding();
                      c.submitStep();
                    },
              child: Text(c.busyStep
                  ? 'Creating…'
                  : sound
                      ? 'Compose sound'
                      : 'Render visual')),
        ]),
        const SizedBox(height: FwLayout.s3),
        if (c.lastResult != null)
          StudioBodyOutput(result: c.lastResult!)
        else
          Padding(
              padding: const EdgeInsets.symmetric(vertical: FwLayout.s4),
              child: Text(c.busyStep
                  ? 'Waiting for the instrument result…'
                  : 'Your ${sound ? 'sound and waveform' : 'rendered frames'} will '
                      'appear here after an authorized action.')),
        if (c.snapshot == null && !c.busySnapshot)
          const Text('Read the current observation before creating an output.'),
        StudioBodyEvidence(controller: c),
      ],
    ));
  }
}

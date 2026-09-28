import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../models/live_screen_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
export '../models/live_screen_models.dart' show ScreenCaptureState;

/// Presentation only. Capture, route admission and frame delivery are owned
/// by the gateway. Constructing this widget never starts a capture session.
class LiveScreenPanel extends StatefulWidget {
  const LiveScreenPanel(
      {super.key,
      required this.sources,
      required this.selected,
      required this.state,
      required this.onSelectionChanged,
      this.hasSession = false,
      this.onStart,
      this.onPause,
      this.onResume,
      this.onStop,
      this.previewSourceId,
      this.onPreviewSourceChanged,
      this.previewBytes,
      this.previewFrame,
      this.delivery,
      this.deliveredFrame,
      this.now,
      this.error});

  final List<LiveScreenSource> sources;
  final Set<String> selected;
  final ScreenCaptureState state;

  /// A disconnected observer does not prove that the gateway stopped capture.
  final bool hasSession;
  final ValueChanged<Set<String>> onSelectionChanged;
  final VoidCallback? onStart, onPause, onResume, onStop;
  final String? previewSourceId;
  final ValueChanged<String>? onPreviewSourceChanged;
  final Uint8List? previewBytes;
  final LiveScreenFrame? previewFrame, deliveredFrame;
  final LiveScreenDelivery? delivery;
  final DateTime Function()? now;
  final String? error;

  @override
  State<LiveScreenPanel> createState() => _LiveScreenPanelState();
}

class _LiveScreenPanelState extends State<LiveScreenPanel> {
  Timer? _clock;
  @override
  void initState() {
    super.initState();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && (widget.delivery != null || widget.previewFrame != null)) {
        setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    super.dispose();
  }

  bool get _active => widget.state == ScreenCaptureState.running;
  bool get _editable =>
      !widget.hasSession &&
      (widget.state == ScreenCaptureState.stopped ||
          widget.state == ScreenCaptureState.disconnected);

  String get _stateLabel => switch (widget.state) {
        ScreenCaptureState.stopped => 'Not sharing',
        ScreenCaptureState.starting => 'Starting capture',
        ScreenCaptureState.running => 'Sharing selected sources',
        ScreenCaptureState.paused => 'Sharing paused',
        ScreenCaptureState.disconnected => 'Disconnected',
      };

  String _deliveryLabel() {
    final delivery = widget.delivery;
    final frame = widget.deliveredFrame;
    if (delivery == null || frame == null || !delivery.matches(frame)) {
      return 'No model delivery recorded';
    }
    final age = delivery.ageAt(widget.now?.call() ?? DateTime.now().toUtc());
    final ageLabel = age == null
        ? 'age unavailable'
        : '${(age.inMilliseconds / 1000).toStringAsFixed(1)}s old';
    final state = !_active
        ? 'Historical delivery'
        : delivery.stale
            ? 'Stale observation'
            : 'Last model delivery';
    return '$state · ${delivery.modeLabel} · $ageLabel';
  }

  String _previewLabel() {
    final frame = widget.previewFrame;
    if (!_active ||
        frame == null ||
        !frame.valid ||
        widget.previewBytes == null) {
      return 'No current local preview';
    }
    final now = widget.now?.call() ?? DateTime.now().toUtc();
    final age = now.difference(frame.capturedAt!);
    final text = age.isNegative
        ? 'age unavailable'
        : '${(age.inMilliseconds / 1000).toStringAsFixed(1)}s old';
    return 'Local preview · ${frame.sourceId} · $text';
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final canStart = widget.selected.isNotEmpty &&
        widget.selected.every((id) => widget.sources
            .any((source) => source.id == id && source.available));
    return HairlineCard(
        child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Screen feed', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: FwLayout.s2),
        Semantics(
            liveRegion: true,
            child: Text(_stateLabel, style: fwMono(t, size: 12))),
        const SizedBox(height: FwLayout.s3),
        if (widget.sources.isEmpty)
          const Text('No capture sources are available.')
        else
          Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
            for (final source in widget.sources)
              FilterChip(
                key: ValueKey('screen-source-${source.id}'),
                label: Text(source.kind == 'synthetic'
                    ? '${source.label} (test source)'
                    : source.label),
                tooltip: source.unavailableReason ?? source.backend,
                selected: widget.selected.contains(source.id),
                onSelected: !_editable || !source.available
                    ? null
                    : (value) {
                        final next = Set<String>.of(widget.selected);
                        if (value) {
                          next.add(source.id);
                        } else {
                          next.remove(source.id);
                        }
                        widget.onSelectionChanged(Set.unmodifiable(next));
                      },
              ),
          ]),
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          if (_editable)
            FilledButton(
                onPressed: canStart ? widget.onStart : null,
                child: const Text('Start sharing')),
          if (_active)
            OutlinedButton(
                onPressed: widget.onPause, child: const Text('Pause')),
          if (widget.state == ScreenCaptureState.paused)
            FilledButton(
                onPressed: widget.onResume, child: const Text('Resume')),
          if (!_editable || widget.hasSession)
            OutlinedButton(
                onPressed: widget.onStop, child: const Text('Stop sharing')),
        ]),
        if (_active && widget.selected.length > 1) ...[
          const SizedBox(height: FwLayout.s2),
          const Text('Preview monitor'),
          Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
            for (final source in widget.sources)
              if (widget.selected.contains(source.id))
                ChoiceChip(
                  key: ValueKey('screen-preview-${source.id}'),
                  label: Text(source.label),
                  selected: widget.previewSourceId == source.id,
                  onSelected: widget.onPreviewSourceChanged == null
                      ? null
                      : (_) => widget.onPreviewSourceChanged!(source.id),
                ),
          ]),
        ],
        const SizedBox(height: FwLayout.s3),
        Container(
          constraints: const BoxConstraints(minHeight: 180, maxHeight: 420),
          decoration: BoxDecoration(
              color: t.ground2, border: Border.all(color: t.line)),
          alignment: Alignment.center,
          child: _active &&
                  widget.previewFrame?.valid == true &&
                  widget.previewBytes != null
              ? Image.memory(widget.previewBytes!,
                  fit: BoxFit.contain,
                  gaplessPlayback: false,
                  semanticLabel: 'Selected screen preview',
                  errorBuilder: (context, error, stack) =>
                      const Text('Preview could not be decoded'))
              : Text(
                  _active
                      ? 'Live preview unavailable'
                      : 'Preview paused or stopped',
                  style: TextStyle(color: t.inkMuted)),
        ),
        const SizedBox(height: FwLayout.s2),
        Text(_previewLabel(), style: fwMono(t, size: 11)),
        const SizedBox(height: FwLayout.s2),
        Text(_deliveryLabel(), style: fwMono(t, size: 11)),
        if (widget.delivery != null &&
            widget.deliveredFrame != null &&
            widget.delivery!.matches(widget.deliveredFrame!))
          Text(
              '${widget.delivery!.model} · ${widget.delivery!.modelRoute} · ${widget.delivery!.sourceId}',
              style: fwMono(t, size: 11)),
        const SizedBox(height: FwLayout.s2),
        Text('The preview and the model receive separate updates.',
            style: TextStyle(color: t.inkMuted, fontSize: 12)),
        if (widget.error != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(widget.error!, style: TextStyle(color: t.ink)),
        ],
      ],
    ));
  }
}

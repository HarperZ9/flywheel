import 'package:flutter/material.dart';

import '../client/continuation_api.dart';
import '../models/continuation_models.dart';
import '../models/journey_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

typedef ContinuationOpen = void Function(String journeyRef, JourneyLens lens);

class ContinuationPanel extends StatefulWidget {
  final ContinuationApi api;
  final bool alive;
  final ContinuationOpen onOpenJourney;
  const ContinuationPanel({
    super.key,
    required this.api,
    required this.alive,
    required this.onOpenJourney,
  });

  @override
  State<ContinuationPanel> createState() => _ContinuationPanelState();
}

class _ContinuationPanelState extends State<ContinuationPanel> {
  final _root = TextEditingController();
  final _export = TextEditingController();
  ContinuationPreview? _preview;
  String? _error;
  String? _message;
  bool _busy = false;

  @override
  void dispose() {
    _root.dispose();
    _export.dispose();
    super.dispose();
  }

  Future<void> _loadPreview() async {
    final root = _root.text.trim();
    if (root.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _message = null;
    });
    try {
      final exportPath = _export.text.trim();
      final result = await widget.api.preview(
          root: root, exportPath: exportPath.isEmpty ? null : exportPath);
      if (mounted) setState(() => _preview = result);
    } on ContinuationApiException catch (error) {
      if (mounted) setState(() => _error = error.failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start() async {
    final preview = _preview;
    if (preview == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _message = null;
    });
    try {
      final result = await widget.api.start(preview);
      widget.onOpenJourney(result.journey.journeyRef, result.openLens);
      if (mounted) {
        setState(() => _message =
            'Journey started from ${result.previewRef.substring(0, 12)}');
      }
    } on ContinuationApiException catch (error) {
      if (mounted) setState(() => _error = error.failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('continue this work'),
        const SizedBox(height: FwLayout.s1),
        Text(
            'Preview the local export and current repo state before starting '
            'a provider-neutral Evidence Journey. Native provider session '
            'resume stays unavailable until a connector proves it.',
            style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
        const SizedBox(height: FwLayout.s3),
        TextField(
          key: const Key('continuation-root'),
          controller: _root,
          enabled: widget.alive && !_busy,
          style: fwMono(t, size: 11.5, color: t.ink),
          decoration:
              const InputDecoration(isDense: true, labelText: 'workspace root'),
        ),
        const SizedBox(height: FwLayout.s2),
        TextField(
          key: const Key('continuation-export'),
          controller: _export,
          enabled: widget.alive && !_busy,
          style: fwMono(t, size: 11.5, color: t.ink),
          decoration: const InputDecoration(
              isDense: true, labelText: 'optional local export'),
        ),
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          FilledButton(
              onPressed: widget.alive && !_busy ? _loadPreview : null,
              child: Text(_busy ? 'Working…' : 'Preview continuation')),
          FilledButton.tonal(
              onPressed: _preview != null && !_busy && _preview!.readyToStart
                  ? _start
                  : null,
              child: const Text('Start Journey')),
          const OutlinedButton(
              onPressed: null, child: Text('Native provider resume')),
        ]),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        if (_message != null) ...[
          const SizedBox(height: FwLayout.s3),
          Text(_message!, style: fwMono(t, size: 11.5, color: t.inkSoft)),
        ],
        if (_preview != null) ...[
          const SizedBox(height: FwLayout.s3),
          _PreviewBlock(_preview!),
        ],
      ]),
    );
  }
}

class _PreviewBlock extends StatelessWidget {
  final ContinuationPreview preview;
  const _PreviewBlock(this.preview);

  String _count(String noun, int count) =>
      '$count $noun${count == 1 ? '' : 's'}';

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(preview.root, style: fwMono(t, size: 11, color: t.inkFaint)),
      const SizedBox(height: FwLayout.s2),
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        VerdictPill(preview.healthState,
            status: preview.readyToStart ? 'verified' : 'drift'),
        Text(
            'branch ${preview.branch} · dirty ${preview.dirtyFiles.length} · '
            'mapped ${preview.mappingCount} · dropped ${preview.dropCount} · '
            'signals ${preview.signalCount}',
            style: fwMono(t, size: 11.5, color: t.ink)),
      ]),
      const SizedBox(height: FwLayout.s2),
      HashText('source', preview.sourceStateSha256, keep: 14),
      if (preview.selectedTaskCount > 0 ||
          preview.selectedFiles.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        Text(
            'private context ${_count('task', preview.selectedTaskCount)} · '
            '${_count('file', preview.selectedFiles.length)}',
            style: fwMono(t, size: 11.5, color: t.ink)),
        if (preview.selectedFiles.isNotEmpty)
          Text(preview.selectedFiles.join(', '),
              style: fwMono(t, size: 11, color: t.inkFaint)),
      ],
      if (!preview.readyToStart) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull('continuation blocked until missing state is restored'),
      ],
      if (preview.providerNativeState == 'unavailable') ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull('provider-native resume unavailable'),
      ],
      for (final row in preview.omissions) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull('${row.code}: ${row.pathHint ?? row.detail}'),
      ],
    ]);
  }
}

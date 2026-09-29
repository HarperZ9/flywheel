import 'dart:async';
import 'package:flutter/material.dart';
import '../models/usage_live_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'usage_live_details.dart';

/// Observes existing local runtimes; never starts a model or a generation.
class UsageLivePanel extends StatefulWidget {
  final Future<Map<String, dynamic>> Function() loadSnapshot;
  final Duration refreshInterval;
  const UsageLivePanel(
      {super.key,
      required this.loadSnapshot,
      this.refreshInterval = const Duration(seconds: 1)});

  @override
  State<UsageLivePanel> createState() => _UsageLivePanelState();
}

class _UsageLivePanelState extends State<UsageLivePanel>
    with WidgetsBindingObserver {
  Timer? _timer;
  UsageLiveSnapshot? _snapshot;
  final _history = <String, List<UsageRatePoint>>{};
  String? _selected;
  bool _paused = false, _background = false, _loading = false, _failed = false;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _background = state != AppLifecycleState.resumed;
    _timer?.cancel();
    if (_background) {
      _generation++;
      _breakHistory();
    } else if (!_paused) {
      _load();
    }
    if (mounted) setState(() {});
  }

  Future<void> _load() async {
    if (_loading || _paused || _background || !mounted) return;
    _loading = true;
    final generation = _generation;
    try {
      final json =
          await widget.loadSnapshot().timeout(const Duration(seconds: 8));
      if (!mounted || generation != _generation) return;
      final next = UsageLiveSnapshot.fromJson(json);
      if (_snapshot != null &&
          !next.observedAt.isAfter(_snapshot!.observedAt)) {
        throw const FormatException('Observation did not advance');
      }
      _history.removeWhere((id, _) => !next.models.any((m) => m.id == id));
      for (final model in next.models) {
        final previous =
            _snapshot?.models.where((m) => m.id == model.id).firstOrNull;
        if (previous != null &&
            (previous.model != model.model ||
                previous.source != model.source)) {
          _history.remove(model.id);
        }
        final history = _history.putIfAbsent(model.id, () => []);
        history
            .add(UsageRatePoint(next.observedAt, model.decode, model.prefill));
        if (history.length > 60) history.removeRange(0, history.length - 60);
      }
      _snapshot = next;
      if (!next.models.any((m) => m.id == _selected)) {
        _selected = next.models.isEmpty ? null : next.models.first.id;
      }
      _failed = false;
    } catch (_) {
      if (!mounted || generation != _generation) return;
      _failed = true;
      _breakHistory();
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        if (!_paused && !_background) {
          _timer = Timer(widget.refreshInterval, _load);
        }
      }
    }
  }

  void _breakHistory() {
    for (final history in _history.values) {
      if (history.isNotEmpty &&
          (history.last.decode != null || history.last.prefill != null)) {
        history.add(UsageRatePoint(history.last.time, null, null));
        if (history.length > 60) history.removeAt(0);
      }
    }
  }

  void _toggle() {
    setState(() {
      _paused = !_paused;
      _generation++;
      _timer?.cancel();
      _breakHistory();
    });
    if (!_paused) _load();
  }

  @override
  void dispose() {
    _generation++;
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final snapshot = _snapshot;
    final status = _paused || _background
        ? 'Paused · last observation retained'
        : _failed
            ? 'Stale · runtime observation unavailable'
            : snapshot == null
                ? 'Reading runtime counters…'
                : 'Observing local runtimes';
    final selected =
        snapshot?.models.where((m) => m.id == _selected).firstOrNull;
    final retainedStatus = _paused || _background
        ? 'paused'
        : _failed
            ? 'stale'
            : null;
    return HairlineCard(
        child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 24,
            runSpacing: 8,
            children: [
              Text('Model activity',
                  style: TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w600, color: t.ink)),
              TextButton.icon(
                  onPressed: _toggle,
                  icon:
                      Icon(_paused ? Icons.play_arrow : Icons.pause, size: 16),
                  label: Text(_paused ? 'Resume' : 'Pause')),
            ]),
        Text(status,
            style:
                TextStyle(fontSize: 12, color: _failed ? t.drift : t.inkMuted)),
        if (snapshot != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(
              'Observed ${snapshot.observedAt.toIso8601String().substring(11, 19)} UTC',
              style: fwMono(t, size: 10, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s4),
          if (snapshot.models.isEmpty)
            const HonestNull(
                'No configured local runtimes are reporting counters. '
                'Configure a local endpoint to observe it here.'),
          for (final model in snapshot.models)
            _modelRow(t, model, retainedStatus: retainedStatus),
          if (selected != null)
            UsageLiveDetails(
                model: selected,
                points: List.unmodifiable(_history[selected.id] ?? [])),
        ] else if (_failed) ...[
          const SizedBox(height: FwLayout.s3),
          const HonestNull(
              'Live counters are unavailable. Observation will retry; '
              'existing usage receipts remain available below.'),
        ],
      ],
    ));
  }

  Widget _modelRow(FwTokens t, UsageLiveModel model, {String? retainedStatus}) {
    final selected = _selected == model.id;
    final label = model.model.isEmpty ? model.endpoint : model.model;
    final state = switch (retainedStatus ?? model.status) {
      'paused' => 'Paused observation',
      'stale' => 'Stale observation',
      'warming_up' => 'Measuring interval',
      'observed' => 'Measured',
      _ => 'Counters unavailable',
    };
    final decode = retainedStatus == null ? model.decode : null;
    return Semantics(
        selected: selected,
        child: TextButton(
          style: TextButton.styleFrom(
              alignment: Alignment.centerLeft,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(FwLayout.radiusSmall)),
              backgroundColor: selected ? t.ground2 : null,
              padding: const EdgeInsets.all(12)),
          onPressed: () => setState(() => _selected = model.id),
          child: LayoutBuilder(
              builder: (context, box) => Wrap(
                    spacing: 24,
                    runSpacing: 8,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                          width: box.maxWidth < 420
                              ? box.maxWidth
                              : box.maxWidth * .5,
                          child: Text(label,
                              style: fwMono(t, size: 12, color: t.inkSoft))),
                      Text(state,
                          style: TextStyle(fontSize: 11, color: t.inkMuted)),
                      Text(usageRate(decode),
                          style: fwMono(t, size: 12, color: t.ink)),
                    ],
                  )),
        ));
  }
}

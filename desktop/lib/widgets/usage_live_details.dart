import 'package:flutter/material.dart';
import '../models/usage_live_models.dart';
import '../theme/flywheel_theme.dart';
import 'usage_rate_chart.dart';

class UsageLiveDetails extends StatelessWidget {
  final UsageLiveModel model;
  final List<UsageRatePoint> points;
  const UsageLiveDetails(
      {super.key, required this.model, required this.points});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: FwLayout.s5),
      LayoutBuilder(builder: (context, box) {
        final decode = UsageRateChart(points: points);
        final prefill = UsageRateChart(points: points, prefill: true);
        if (box.maxWidth < 640) {
          return Column(
              children: [decode, const SizedBox(height: 24), prefill]);
        }
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: decode),
          const SizedBox(width: 32),
          Expanded(child: prefill),
        ]);
      }),
      const SizedBox(height: FwLayout.s5),
      Wrap(spacing: 32, runSpacing: 16, children: [
        _counter(t, 'Generated tokens', usageCount(model.generated)),
        _counter(t, 'Prompt tokens', usageCount(model.prompt)),
        _counter(t, 'Power draw', 'Not reported'),
      ]),
      const SizedBox(height: FwLayout.s4),
      if (model.reason.isNotEmpty) ...[
        Text(model.reason, style: TextStyle(fontSize: 12, color: t.inkMuted)),
        const SizedBox(height: FwLayout.s2),
      ],
      Text(
          switch (model.counterScope) {
            'current_request' => 'Current request counters',
            'current_runtime' => 'Current runtime counters',
            _ => 'Counter scope not reported',
          },
          style: TextStyle(fontSize: 12, color: t.inkMuted)),
      if (model.intervalSeconds != null)
        Text(
            'Measured interval: ${model.intervalSeconds!.toStringAsFixed(2)} s',
            style: fwMono(t, size: 11, color: t.inkMuted)),
      Text(
          'Runtime counters · ${model.source.isEmpty ? 'Source unavailable' : model.source}',
          style: fwMono(t, size: 11, color: t.inkMuted)),
      const SizedBox(height: FwLayout.s2),
      Text(
          'Counters can reset when a request or runtime restarts. Rates use '
          'measured counter changes; they do not measure answer quality. '
          'Signed answer totals remain below.',
          style: TextStyle(fontSize: 12, height: 1.5, color: t.inkMuted)),
    ]);
  }

  Widget _counter(FwTokens t, String label, String value) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 12, color: t.inkMuted)),
          const SizedBox(height: 4),
          Text(value, style: fwMono(t, size: 15, color: t.inkSoft)),
        ],
      );
}

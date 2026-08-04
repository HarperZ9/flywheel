// escalate_row.dart — the Companion escalate branch made operable: pick a
// stronger endpoint, optionally pick WHICH model it serves, and actually
// route the prompt, receipt included. Dumb widget: state and callbacks in,
// no client.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'model_picker.dart';
import 'model_selector.dart';

class EscalateRouteRow extends StatelessWidget {
  final List<EndpointRow> endpoints;

  /// The chosen escalate endpoint, or null before one is picked.
  final String? endpoint;

  /// The chosen model override for [endpoint]; null/empty means its default.
  final String? model;
  final bool routing;
  final Map<String, dynamic>? routed;
  final String? routeError;
  final ValueChanged<String> onEndpoint;

  /// Fires with the picked model id; '' means "use the endpoint default".
  final ValueChanged<String> onModel;
  final Future<Map<String, dynamic>> Function() loadModels;
  final VoidCallback onRoute;

  const EscalateRouteRow({
    super.key,
    required this.endpoints,
    required this.endpoint,
    required this.model,
    required this.routing,
    required this.routed,
    required this.routeError,
    required this.onEndpoint,
    required this.onModel,
    required this.loadModels,
    required this.onRoute,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(
        spacing: FwLayout.s3,
        runSpacing: FwLayout.s2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          if (endpoints.isNotEmpty)
            ModelPickerButton(
              endpoints: endpoints,
              current: endpoint,
              enabled: !routing,
              onSelect: onEndpoint,
            )
          else
            Text('no endpoints in the roster',
                style: fwMono(t, size: 11, color: t.inkFaint)),
          if (endpoint != null)
            ModelSelectorButton(
              loadModels: loadModels,
              current: model,
              enabled: !routing,
              onSelect: onModel,
            ),
          FilledButton.tonal(
            onPressed: (endpoint == null || routing) ? null : onRoute,
            child: Text(routing ? 'Routing…' : 'Route it'),
          ),
        ],
      ),
      if (routeError != null) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull('Route failed: $routeError'),
      ],
      if (routed != null) ...[
        const SizedBox(height: FwLayout.s3),
        VerdictPill('routed · $endpoint', status: 'drift'),
        const SizedBox(height: FwLayout.s2),
        SelectableText('${routed!['text'] ?? routed!['error'] ?? ''}',
            style: fwMono(t, size: 12.5).copyWith(height: 1.55)),
        if ('${routed!['receipt'] ?? ''}'.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          HashText('receipt', '${routed!['receipt']}', keep: 32),
        ],
      ],
    ]);
  }
}

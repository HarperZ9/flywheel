// start_task_route_card.dart — model/access/cost disclosure for StartTaskPrelude.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'model_picker.dart';
import 'model_selector.dart';

class StartTaskRouteCard extends StatelessWidget {
  final List<EndpointRow> endpoints;
  final String? endpoint;
  final String? chosenModel;
  final bool enabled;
  final ValueChanged<String> onEndpoint;
  final ValueChanged<String> onModel;
  final Future<Map<String, dynamic>> Function() loadModels;

  const StartTaskRouteCard({
    super.key,
    required this.endpoints,
    required this.endpoint,
    required this.chosenModel,
    required this.enabled,
    required this.onEndpoint,
    required this.onModel,
    required this.loadModels,
  });

  EndpointRow? get _selected {
    final name = endpoint;
    if (name == null) return null;
    for (final row in endpoints) {
      if (row.name == name) return row;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final selected = _selected;
    return Container(
      padding: const EdgeInsets.all(FwLayout.s3),
      decoration: BoxDecoration(
        color: t.ground2,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.hairline),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Model, access, cost',
            style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              key: const Key('start-task-model-picker'),
              height: 44,
              child: ModelPickerButton(
                endpoints: endpoints,
                current: endpoint,
                onSelect: onEndpoint,
                enabled: enabled,
              ),
            ),
            if (endpoint != null)
              SizedBox(
                height: 44,
                child: ModelSelectorButton(
                  key: const Key('start-task-model-selector'),
                  loadModels: loadModels,
                  current: chosenModel,
                  onSelect: onModel,
                  enabled: enabled,
                ),
              ),
          ],
        ),
        const SizedBox(height: FwLayout.s2),
        Text(selected == null ? 'No model route selected.' : _access(selected),
            style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
        const SizedBox(height: 2),
        Text(
            selected == null
                ? 'Choose a route before sending.'
                : 'Cost not reported by this route.',
            style: fwMono(t, size: 11.5, color: t.inkFaint)),
      ]),
    );
  }
}

String _access(EndpointRow row) => switch (row.credential) {
      'cli-auth' when row.cliAuthenticated => 'Subscription access',
      'cli-auth' => 'Sign-in needed',
      'present' => 'API key route',
      'local-none' => 'Local endpoint',
      _ => 'Not ready',
    };

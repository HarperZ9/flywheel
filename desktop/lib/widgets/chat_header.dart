// chat_header.dart — the Chat surface header: mode chips, the endpoint
// picker, the per-endpoint model selector, and the witness line. Dumb
// widget: state and callbacks in, no client.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'mode_chip.dart';
import 'model_picker.dart';
import 'model_selector.dart';

class ChatHeader extends StatelessWidget {
  final bool agentMode;
  final bool streaming;
  final List<EndpointRow> endpoints;

  /// The chosen endpoint name (the roster row), or null before one exists.
  final String? endpoint;

  /// The chosen model override for [endpoint]; null/empty means its default.
  final String? chosenModel;
  final ValueChanged<bool> onMode;
  final ValueChanged<String> onEndpoint;

  /// Fires with the picked model id; '' means "use the endpoint default".
  final ValueChanged<String> onModel;
  final Future<Map<String, dynamic>> Function() loadModels;

  const ChatHeader({
    super.key,
    required this.agentMode,
    required this.streaming,
    required this.endpoints,
    required this.endpoint,
    required this.chosenModel,
    required this.onMode,
    required this.onEndpoint,
    required this.onModel,
    required this.loadModels,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return LayoutBuilder(
        builder: (context, constraints) => Container(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s5, vertical: FwLayout.s3),
            decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: t.hairline))),
            child: _row(context, t, constraints.maxWidth >= 650)));
  }

  Widget _row(BuildContext context, FwTokens t, bool showReceiptCopy) =>
      Row(children: [
        Text('Chat', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(width: FwLayout.s4),
        FwModeChip(
            label: 'chat',
            active: !agentMode,
            onTap: () {
              if (!streaming) onMode(false);
            }),
        const SizedBox(width: FwLayout.s1),
        FwModeChip(
            label: 'agent',
            active: agentMode,
            onTap: () {
              if (!streaming) onMode(true);
            }),
        const SizedBox(width: FwLayout.s4),
        if (!agentMode && endpoints.isNotEmpty)
          ModelPickerButton(
            endpoints: endpoints,
            current: endpoint,
            enabled: !streaming,
            onSelect: onEndpoint,
          ),
        if (!agentMode && endpoint != null && showReceiptCopy) ...[
          const SizedBox(width: FwLayout.s2),
          ModelSelectorButton(
            loadModels: loadModels,
            current: chosenModel,
            enabled: !streaming,
            onSelect: onModel,
          ),
        ],
        if (showReceiptCopy) ...[
          const Spacer(),
          Flexible(
            child: Text(
                agentMode
                    ? 'every run persists with its trace'
                    : 'receipt state shown on every reply',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ),
        ],
      ]);
}

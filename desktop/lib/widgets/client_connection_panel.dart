import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/client_connection_preview.dart';
import '../theme/flywheel_theme.dart';

/// Keeps the optional connection task out of the plugin registration form.
class ClientConnectionAction extends StatelessWidget {
  const ClientConnectionAction({super.key, this.preview});
  final ClientConnectionPreview? preview;

  @override
  Widget build(BuildContext context) => OutlinedButton(
        onPressed: () => showDialog<void>(
          context: context,
          builder: (context) => AlertDialog(
            scrollable: true,
            insetPadding: const EdgeInsets.all(FwLayout.s4),
            title: const Text('Local client tools'),
            content: SizedBox(
              width: 640,
              child: ClientConnectionPanel(preview: preview),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Close'),
              ),
            ],
          ),
        ),
        child: const Text('Connect a local client'),
      );
}

/// App-owned preview. Never reads or edits another client's configuration.
class ClientConnectionPanel extends StatefulWidget {
  const ClientConnectionPanel({super.key, this.preview});
  final ClientConnectionPreview? preview;

  @override
  State<ClientConnectionPanel> createState() => _ClientConnectionPanelState();
}

class _ClientConnectionPanelState extends State<ClientConnectionPanel> {
  ClientConfigFormat _format = ClientConfigFormat.codexToml;
  String? _copyStatus;
  bool _copying = false;

  Future<void> _copy(String snippet) async {
    setState(() => _copying = true);
    String status;
    try {
      await Clipboard.setData(ClipboardData(text: snippet));
      status = 'Configuration copied. Connection not tested.';
    } catch (_) {
      status = 'Could not copy. Select the preview text and copy it manually.';
    }
    if (mounted) {
      setState(() {
        _copying = false;
        _copyStatus = status;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final preview = widget.preview ?? ClientConnectionPreview.resolve();
    final snippet = preview.snippet(_format);
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Use Articulate in another local client',
            style: theme.textTheme.titleMedium),
        const SizedBox(height: FwLayout.s2),
        const Text(
            'Review text and check edits with the model you already use. '
            'No model or publisher service is included.'),
        const SizedBox(height: FwLayout.s2),
        const Text('Restricted profile: supplied text only. No file tools, '
            'shell commands or network backends. Your client and model '
            'have their own data handling and costs.'),
        const SizedBox(height: FwLayout.s3),
        Text(preview.reason),
        const SizedBox(height: FwLayout.s3),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            for (final format in ClientConfigFormat.values)
              ChoiceChip(
                label: Text(format == ClientConfigFormat.codexToml
                    ? 'Codex (TOML)'
                    : 'MCP JSON'),
                selected: _format == format,
                onSelected: (_) => setState(() {
                  _format = format;
                  _copyStatus = null;
                }),
              ),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        if (snippet != null) ...[
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(FwLayout.s3),
            color: context.fw.ground2,
            child: SelectableText(snippet,
                style: TextStyle(
                    fontFamily: context.fw.monoFamily,
                    color: context.fw.ink,
                    fontSize: 12.5)),
          ),
          const SizedBox(height: FwLayout.s3),
        ],
        const Text('Preview only. Copy this entry into a supported local '
            'client after reviewing its configuration. Keep existing entries. '
            'Flywheel does not change client settings or test the connection.'),
        const SizedBox(height: FwLayout.s3),
        OutlinedButton(
          onPressed: snippet == null || _copying ? null : () => _copy(snippet),
          child: Text(_copying ? 'Copying…' : 'Copy configuration'),
        ),
        if (_copyStatus != null) ...[
          const SizedBox(height: FwLayout.s2),
          Semantics(liveRegion: true, child: Text(_copyStatus!)),
        ],
      ],
    );
  }
}

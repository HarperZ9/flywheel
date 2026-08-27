// connection_panel.dart -- pair this device with a gateway, no config file.
//
// Desktop default is the engine on this machine. To use the SAME app against
// another machine (a phone reaching the PC), paste that gateway's address and a
// paired token here; the app then talks to that gateway. The token is a bearer for
// the operator's OWN gateway, kept on this device and never shown back, never a
// model-provider key. A paired connection applies on the next launch.

import 'package:flutter/material.dart';

import '../services/connection_config.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

Future<void> showConnectionPanel(BuildContext context, {ConnectionStore? store}) {
  return showDialog(
    context: context,
    builder: (ctx) => Dialog(
      backgroundColor: ctx.fw.ground,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 440),
        child: Padding(
          padding: const EdgeInsets.all(FwLayout.s5),
          child: ConnectionForm(store: store ?? ConnectionStore()),
        ),
      ),
    ),
  );
}

class ConnectionForm extends StatefulWidget {
  final ConnectionStore store;
  const ConnectionForm({super.key, required this.store});

  @override
  State<ConnectionForm> createState() => _ConnectionFormState();
}

class _ConnectionFormState extends State<ConnectionForm> {
  late final TextEditingController _url;
  late final TextEditingController _token;
  String? _note;

  @override
  void initState() {
    super.initState();
    final c = widget.store.load();
    _url = TextEditingController(text: c.baseUrl ?? '');
    _token = TextEditingController(text: c.token ?? '');
  }

  @override
  void dispose() {
    _url.dispose();
    _token.dispose();
    super.dispose();
  }

  void _save() {
    final url = _url.text.trim();
    final token = _token.text.trim();
    widget.store.save(ConnectionConfig(
      baseUrl: url.isEmpty ? null : url,
      token: token.isEmpty ? null : token,
    ));
    setState(() => _note = url.isEmpty
        ? 'Cleared. This device uses its own engine on next launch.'
        : 'Paired with $url. Applied on next launch.');
  }

  void _clear() {
    widget.store.clear();
    _url.clear();
    _token.clear();
    setState(() => _note = 'Cleared. Back to the local engine on next launch.');
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('connection', hot: true),
        const SizedBox(height: FwLayout.s2),
        const Text('This device, one gateway.',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        const SizedBox(height: FwLayout.s2),
        Text(
            'Leave blank to use the engine on this machine. To run the same app '
            'against another machine, paste that gateway address and a paired token.',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s4),
        Text('Gateway address', style: fwMono(t, size: 10, color: t.inkMuted)),
        const SizedBox(height: FwLayout.s1),
        TextField(
          key: const Key('connection-url'),
          controller: _url,
          autocorrect: false,
          enableSuggestions: false,
          style: fwMono(t, size: 11),
          decoration: const InputDecoration(
              isDense: true, hintText: 'https://your-pc.example'),
        ),
        const SizedBox(height: FwLayout.s3),
        Text('Paired token', style: fwMono(t, size: 10, color: t.inkMuted)),
        const SizedBox(height: FwLayout.s1),
        TextField(
          key: const Key('connection-token'),
          controller: _token,
          obscureText: true, // the value is never shown back
          autocorrect: false,
          enableSuggestions: false,
          style: fwMono(t, size: 11),
          decoration:
              const InputDecoration(isDense: true, hintText: 'the gateway token'),
        ),
        const SizedBox(height: FwLayout.s2),
        const HonestNull(
            'A paired connection is applied on the next launch. The token is a bearer '
            'for your own gateway, kept on this device, and never shown back.'),
        if (_note != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(_note!, style: fwMono(t, size: 10.5, color: t.inkMuted)),
        ],
        const SizedBox(height: FwLayout.s4),
        Row(children: [
          FilledButton(onPressed: _save, child: const Text('Pair')),
          const SizedBox(width: FwLayout.s2),
          TextButton(onPressed: _clear, child: const Text('Use local engine')),
        ]),
      ],
    );
  }
}

// tool_call_sheet.dart — run one probed tool. The probe proves a server
// offers a tool and its argument schema; this sheet closes the loop by
// actually calling it. A schema-driven Form renders the tool's declared
// arguments as labeled fields (the default); Raw JSON stays as the advanced
// fallback for anything the form cannot express. Either way, the arguments go
// out well-typed and the server's own result comes back verbatim.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/tool_spec.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'tool_form.dart';

void showToolCallSheet(BuildContext context, GatewayClient client,
    String plugin, ToolSpec spec) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: context.fw.ground,
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(
          left: FwLayout.s5,
          right: FwLayout.s5,
          top: FwLayout.s5,
          bottom: MediaQuery.of(ctx).viewInsets.bottom + FwLayout.s5),
      child: ToolCallSheet(client: client, plugin: plugin, spec: spec),
    ),
  );
}

class ToolCallSheet extends StatefulWidget {
  final GatewayClient client;
  final String plugin;
  final ToolSpec spec;
  const ToolCallSheet(
      {super.key,
      required this.client,
      required this.plugin,
      required this.spec});

  @override
  State<ToolCallSheet> createState() => _ToolCallSheetState();
}

class _ToolCallSheetState extends State<ToolCallSheet> {
  final _args = TextEditingController(text: '{}');
  bool _raw = false; // Form is the default; Raw JSON is the fallback.
  Map<String, dynamic> _formArgs = const {};
  List<String> _missing = const [];
  bool _calling = false;
  String? _result;
  String? _error;

  @override
  void dispose() {
    _args.dispose();
    super.dispose();
  }

  /// Resolve the arguments to send, or set an error and return null.
  Map<String, dynamic>? _resolveArgs() {
    if (!_raw) {
      if (_missing.isNotEmpty) {
        setState(() =>
            _error = 'fill the required field(s): ${_missing.join(', ')}');
        return null;
      }
      return _formArgs;
    }
    try {
      final parsed = jsonDecode(_args.text.trim().isEmpty ? '{}' : _args.text);
      if (parsed is! Map<String, dynamic>) {
        setState(() => _error = 'arguments must be a JSON object');
        return null;
      }
      return parsed;
    } catch (e) {
      setState(() => _error = 'arguments are not valid JSON: $e');
      return null;
    }
  }

  Future<void> _call() async {
    if (_calling) return;
    final arguments = _resolveArgs();
    if (arguments == null) return;
    setState(() {
      _calling = true;
      _error = null;
      _result = null;
    });
    try {
      final doc = await widget.client
          .callPlugin(widget.plugin, widget.spec.name, arguments);
      if (mounted) {
        setState(
            () => _result = const JsonEncoder.withIndent('  ').convert(doc));
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _calling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final desc = widget.spec.description;
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Row(children: [
        Expanded(
          child: Text('${widget.plugin} · ${widget.spec.name}',
              style: fwMono(t, size: 12.5)),
        ),
        FilledButton(
          onPressed: _calling ? null : _call,
          child: Text(_calling ? 'Calling…' : 'Call'),
        ),
      ]),
      if (desc.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        Align(
          alignment: Alignment.centerLeft,
          child: Text(desc,
              style: TextStyle(fontSize: 12, color: t.inkMuted, height: 1.4)),
        ),
      ],
      const SizedBox(height: FwLayout.s3),
      _modeToggle(t),
      const SizedBox(height: FwLayout.s3),
      _raw ? _rawField(t) : _formBody(),
      if (_error != null) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull(_error!),
      ],
      if (_result != null) ...[
        const SizedBox(height: FwLayout.s3),
        ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 300),
          child: SingleChildScrollView(
            child: Align(
              alignment: Alignment.centerLeft,
              child: SelectableText(_result!,
                  style: fwMono(t, size: 11).copyWith(height: 1.5)),
            ),
          ),
        ),
      ],
    ]);
  }

  Widget _formBody() {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 360),
      child: SingleChildScrollView(
        child: ToolForm(
          spec: widget.spec,
          onChanged: (args, missing) {
            _formArgs = args;
            _missing = missing;
          },
        ),
      ),
    );
  }

  Widget _rawField(FwTokens t) {
    return TextField(
      controller: _args,
      maxLines: 5,
      minLines: 2,
      style: fwMono(t, size: 12),
      decoration:
          const InputDecoration(hintText: 'arguments as a JSON object'),
    );
  }

  Widget _modeToggle(FwTokens t) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _modeChip(t, 'Form', !_raw, () => setState(() => _raw = false)),
          const SizedBox(width: FwLayout.s2),
          _modeChip(t, 'Raw JSON', _raw, () => setState(() => _raw = true)),
        ],
      ),
    );
  }

  Widget _modeChip(FwTokens t, String label, bool active, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: active ? t.drift.withValues(alpha: 0.10) : t.ground2,
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
          border: Border.all(
              color: active ? t.drift.withValues(alpha: 0.42) : t.line),
        ),
        child: Text(label.toUpperCase(),
            style: fwKicker(t,
                size: 10, color: active ? t.drift : t.inkFaint)),
      ),
    );
  }
}

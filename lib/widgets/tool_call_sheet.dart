// tool_call_sheet.dart — run one probed tool. The probe proves a server
// offers a tool; this sheet closes the loop by actually calling it: JSON
// arguments in, the server's own result verbatim out. A malformed argument
// document is refused client-side before it ever reaches the wire.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

void showToolCallSheet(
    BuildContext context, GatewayClient client, String plugin, String tool) {
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
      child: ToolCallSheet(client: client, plugin: plugin, tool: tool),
    ),
  );
}

class ToolCallSheet extends StatefulWidget {
  final GatewayClient client;
  final String plugin;
  final String tool;
  const ToolCallSheet(
      {super.key,
      required this.client,
      required this.plugin,
      required this.tool});

  @override
  State<ToolCallSheet> createState() => _ToolCallSheetState();
}

class _ToolCallSheetState extends State<ToolCallSheet> {
  final _args = TextEditingController(text: '{}');
  bool _calling = false;
  String? _result;
  String? _error;

  @override
  void dispose() {
    _args.dispose();
    super.dispose();
  }

  Future<void> _call() async {
    if (_calling) return;
    final Map<String, dynamic> arguments;
    try {
      final parsed = jsonDecode(_args.text.trim().isEmpty ? '{}' : _args.text);
      if (parsed is! Map<String, dynamic>) {
        setState(() => _error = 'arguments must be a JSON object');
        return;
      }
      arguments = parsed;
    } catch (e) {
      setState(() => _error = 'arguments are not valid JSON: $e');
      return;
    }
    setState(() {
      _calling = true;
      _error = null;
      _result = null;
    });
    try {
      final doc =
          await widget.client.callPlugin(widget.plugin, widget.tool, arguments);
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
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Row(children: [
        Text('${widget.plugin} · ${widget.tool}', style: fwMono(t, size: 12.5)),
        const Spacer(),
        FilledButton(
          onPressed: _calling ? null : _call,
          child: Text(_calling ? 'Calling…' : 'Call'),
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      TextField(
        controller: _args,
        maxLines: 4,
        minLines: 2,
        style: fwMono(t, size: 12),
        decoration:
            const InputDecoration(hintText: 'arguments as a JSON object'),
      ),
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
}

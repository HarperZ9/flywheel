// tool_form.dart — render a tool's JSON Schema as labeled argument fields.
//
// This is the keystone widget: it turns an MCP/lane tool's inputSchema into
// real inputs (typed, required-marked, default-seeded) so ~100 lane/MCP tools
// become fillable in-app instead of a blind {} JSON box. It produces a
// well-typed arguments Map and reports which required fields are still empty;
// the caller decides whether the call may proceed. A schema it cannot express
// (nested objects, unions) still works through the raw-JSON fallback the sheet
// keeps beside this form.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/tool_spec.dart';
import '../theme/flywheel_theme.dart';

class ToolForm extends StatefulWidget {
  final ToolSpec spec;

  /// Fired on every edit (and once after first layout) with the current
  /// well-typed arguments and the still-empty required field names.
  final void Function(Map<String, dynamic> args, List<String> missingRequired)
      onChanged;

  const ToolForm({super.key, required this.spec, required this.onChanged});

  @override
  State<ToolForm> createState() => _ToolFormState();
}

class _ToolFormState extends State<ToolForm> {
  final Map<String, TextEditingController> _text = {};

  /// Present values for non-text controls (booleans, enums). A key is absent
  /// until the user sets it or the schema seeds a default — so an untouched
  /// optional flag is never sent, and a server-side default is never clobbered.
  final Map<String, dynamic> _explicit = {};

  @override
  void initState() {
    super.initState();
    for (final e in widget.spec.properties) {
      final schema = e.value;
      final def = schema['default'];
      if (_hasEnum(schema)) {
        if (def != null) _explicit[e.key] = '$def';
      } else if (_typeOf(schema) == 'boolean') {
        if (def is bool) _explicit[e.key] = def;
      } else {
        _text[e.key] = TextEditingController(
            text: def == null
                ? ''
                : (def is String ? def : jsonEncode(def)));
      }
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _emit());
  }

  @override
  void dispose() {
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _emit() {
    final args = _buildArgs();
    final propKeys = widget.spec.properties.map((e) => e.key).toSet();
    final missing = widget.spec.requiredFields
        .where((k) => propKeys.contains(k) && !args.containsKey(k))
        .toList();
    widget.onChanged(args, missing);
  }

  void _onEdit() {
    setState(() {});
    _emit();
  }

  bool _hasEnum(Map schema) {
    final e = schema['enum'];
    return e is List && e.isNotEmpty;
  }

  String _typeOf(Map schema) {
    final t = schema['type'];
    if (t is String) return t;
    if (t is List && t.isNotEmpty) return '${t.first}';
    return 'string';
  }

  List<String> _enumValues(Map schema) =>
      (schema['enum'] as List).map((e) => '$e').toList();

  String _itemsType(Map schema) {
    final items = schema['items'];
    return (items is Map) ? '${items['type'] ?? ''}' : '';
  }

  String _typeLabel(Map schema) {
    if (_hasEnum(schema)) return 'enum';
    final t = _typeOf(schema);
    if (t == 'array') {
      final it = _itemsType(schema);
      return it.isEmpty ? 'array' : 'array<$it>';
    }
    return t;
  }

  Map<String, dynamic> _buildArgs() {
    final args = <String, dynamic>{};
    for (final e in widget.spec.properties) {
      final key = e.key;
      final schema = e.value;
      if (_hasEnum(schema)) {
        if (_explicit[key] != null) args[key] = _explicit[key];
        continue;
      }
      final type = _typeOf(schema);
      if (type == 'boolean') {
        if (_explicit.containsKey(key)) args[key] = _explicit[key];
        continue;
      }
      final txt = _text[key]?.text.trim() ?? '';
      if (txt.isEmpty) continue;
      final v = _coerce(type, schema, txt);
      if (v != null) args[key] = v;
    }
    return args;
  }

  dynamic _coerce(String type, Map schema, String text) {
    switch (type) {
      case 'integer':
        return int.tryParse(text);
      case 'number':
        return num.tryParse(text);
      case 'array':
        return _coerceArray(schema, text);
      case 'object':
        try {
          final v = jsonDecode(text);
          return v is Map ? v : null;
        } catch (_) {
          return null;
        }
      default:
        return text;
    }
  }

  dynamic _coerceArray(Map schema, String text) {
    if (text.startsWith('[')) {
      try {
        final v = jsonDecode(text);
        if (v is List) return v;
      } catch (_) {/* fall through to line/comma split */}
    }
    final parts = text
        .split(RegExp(r'[\n,]'))
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    final it = _itemsType(schema);
    if (it == 'integer' || it == 'number') {
      final nums = parts
          .map((p) => it == 'integer' ? int.tryParse(p) : num.tryParse(p))
          .toList();
      return nums.any((n) => n == null) ? null : nums;
    }
    return parts;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final props = widget.spec.properties;
    if (props.isEmpty) {
      return Text('This tool declares no arguments. Call it as is, or use '
          'Raw JSON if it accepts undeclared fields.',
          style: TextStyle(fontSize: 12, color: t.inkMuted, height: 1.4));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [for (final e in props) _field(t, e.key, e.value)],
    );
  }

  Widget _field(FwTokens t, String key, Map<String, dynamic> schema) {
    final required = widget.spec.requiredFields.contains(key);
    final desc = '${schema['description'] ?? ''}';
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(key, style: fwMono(t, size: 12, weight: FontWeight.w600)),
              if (required)
                Text(' *',
                    style: fwMono(t, size: 12, weight: FontWeight.w700)
                        .copyWith(color: t.drift)),
              const Spacer(),
              Text(_typeLabel(schema).toUpperCase(),
                  style: fwKicker(t, size: 9.5, color: t.inkFaint)),
            ],
          ),
          const SizedBox(height: FwLayout.s1),
          _control(t, key, schema),
          if (desc.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(desc,
                style: TextStyle(fontSize: 11, color: t.inkFaint, height: 1.35)),
          ],
        ],
      ),
    );
  }

  Widget _control(FwTokens t, String key, Map<String, dynamic> schema) {
    if (_hasEnum(schema)) {
      final values = _enumValues(schema);
      return DropdownButtonFormField<String>(
        initialValue: _explicit[key] as String?,
        isExpanded: true,
        style: fwMono(t, size: 12.5, color: t.ink),
        decoration: const InputDecoration(hintText: 'select…'),
        items: [
          for (final v in values)
            DropdownMenuItem(value: v, child: Text(v)),
        ],
        onChanged: (v) {
          _explicit[key] = v;
          _onEdit();
        },
      );
    }
    final type = _typeOf(schema);
    if (type == 'boolean') {
      final on = (_explicit[key] as bool?) ?? false;
      return Row(
        children: [
          Switch(
            value: on,
            onChanged: (v) {
              _explicit[key] = v;
              _onEdit();
            },
          ),
          const SizedBox(width: FwLayout.s2),
          Text(on ? 'true' : 'false', style: fwMono(t, size: 12)),
        ],
      );
    }
    final numeric = type == 'integer' || type == 'number';
    final txt = _text[key]!.text.trim();
    final badNumber = numeric &&
        txt.isNotEmpty &&
        (type == 'integer' ? int.tryParse(txt) : num.tryParse(txt)) == null;
    final isArray = type == 'array';
    return TextField(
      controller: _text[key],
      style: fwMono(t, size: 12.5),
      minLines: 1,
      maxLines: isArray ? 3 : 1,
      keyboardType: numeric
          ? const TextInputType.numberWithOptions(signed: true, decimal: true)
          : (isArray ? TextInputType.multiline : TextInputType.text),
      decoration: InputDecoration(
        hintText: isArray
            ? 'one per line or comma-separated'
            : (numeric ? 'a $type' : 'value'),
        errorText: badNumber ? 'expects $type' : null,
      ),
      onChanged: (_) => _onEdit(),
    );
  }
}

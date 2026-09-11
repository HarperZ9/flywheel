import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/operation_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class OutputCheckPanel extends StatefulWidget {
  final GatewayClient client;
  const OutputCheckPanel({super.key, required this.client});

  @override
  State<OutputCheckPanel> createState() => _OutputCheckPanelState();
}

class _OutputCheckPanelState extends State<OutputCheckPanel> {
  final _contractPath = TextEditingController();
  final _contractSha = TextEditingController();
  final _answerPath = TextEditingController();
  final _answerSha = TextEditingController();
  final _authoritySources = TextEditingController();
  bool _allowCommands = false, _strict = false, _busy = false;
  OperationResult? _result;
  String? _error;
  GatewayOperation? _pending;

  @override
  void dispose() {
    _contractPath.dispose();
    _contractSha.dispose();
    _answerPath.dispose();
    _answerSha.dispose();
    _authoritySources.dispose();
    super.dispose();
  }

  Future<void> _check() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      final operation = _operation();
      _pending = operation;
      final result = await authorizeGatewayOperation<OperationResult?>(
        context,
        operation,
        _dispatch,
        currentOperation: () => _pending,
      );
      if (mounted && result != null) setState(() => _result = result);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      _pending = null;
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<OperationResult?> _dispatch(Map<String, dynamic> body) async {
    await for (final event in GatewayOperations(widget.client).start(
      body,
      path: '/api/output/check',
    )) {
      if (event.result != null) return event.result;
      if (event.isDone) break;
    }
    return null;
  }

  GatewayOperation _operation() {
    final contractSha = _sha(_contractSha.text);
    final answerSha = _sha(_answerSha.text);
    final authoritySources = _authoritySourceRefs();
    final operation = <String, Object?>{
      'contract': _source(_contractPath.text, contractSha),
      'answer': _source(_answerPath.text, answerSha),
      'authority_sources': authoritySources,
      'allow_commands': _allowCommands,
      'strict': _strict,
      'json': true,
      'stream': true,
    };
    return GatewayOperation.exact(
      action: 'output.check',
      clientRequestId: 'output-check-${DateTime.now().microsecondsSinceEpoch}',
      operation: operation,
      dataRefs: [
        'data_output_check.contract:${contractSha.substring(0, 32)}',
        'data_output_check.answer:${answerSha.substring(0, 32)}',
        for (final item in authoritySources.indexed)
          'data_output_check.authority.${item.$1}:'
              '${(item.$2['sha256'] as String).substring(0, 32)}',
      ],
      credentialRefs: const [],
    );
  }

  List<Map<String, Object?>> _authoritySourceRefs() {
    final sources = <Map<String, Object?>>[];
    for (final raw in _authoritySources.text.split(RegExp(r'\r?\n'))) {
      final line = raw.trim();
      if (line.isEmpty) continue;
      final parts = line.split(RegExp(r'\s+'));
      if (parts.length != 2) {
        throw ArgumentError('authority sources use: path sha256');
      }
      sources.add(_source(parts[0], _sha(parts[1])));
    }
    return sources;
  }

  Map<String, Object?> _source(String path, String sha) => {
        'kind': 'workspace-file',
        'path': path.trim(),
        'sha256': sha,
      };

  String _sha(String value) {
    final clean = value.trim().toLowerCase();
    if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(clean)) {
      throw ArgumentError('sha256 must be 64 lowercase hex characters');
    }
    return clean;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('output check · source-bound release gate'),
        const SizedBox(height: FwLayout.s3),
        Text('Check an answer against the contract sources before release.',
            style: TextStyle(color: t.inkMuted, fontSize: 12.5)),
        const SizedBox(height: FwLayout.s3),
        _field(
            _contractPath,
            'contract path',
            'examples/output-validation/form-1040.contract.json',
            'output-check-contract-path'),
        const SizedBox(height: FwLayout.s2),
        _field(
            _contractSha, 'contract sha256', '', 'output-check-contract-sha'),
        const SizedBox(height: FwLayout.s2),
        _field(
            _answerPath,
            'answer path',
            'examples/output-validation/answer.json',
            'output-check-answer-path'),
        const SizedBox(height: FwLayout.s2),
        _field(_answerSha, 'answer sha256', '', 'output-check-answer-sha'),
        const SizedBox(height: FwLayout.s2),
        _field(
            _authoritySources,
            'authority source refs',
            'one per line: rows.json <sha256>',
            'output-check-authority-sources',
            maxLines: 3),
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
          FilterChip(
            key: const ValueKey('output-check-allow-commands'),
            selected: _allowCommands,
            label: const Text('allow command authorities'),
            onSelected:
                _busy ? null : (v) => setState(() => _allowCommands = v),
          ),
          FilterChip(
            selected: _strict,
            label: const Text('strict release exit'),
            onSelected: _busy ? null : (v) => setState(() => _strict = v),
          ),
          FilledButton(
            onPressed: _busy ? null : _check,
            child: Text(_busy ? 'Checking…' : 'Check output'),
          ),
        ]),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('The output check did not run: $_error'),
        ],
        if (_result != null) ...[
          const SizedBox(height: FwLayout.s3),
          _resultBlock(t, _result!),
        ],
      ]),
    );
  }

  Widget _field(TextEditingController c, String label, String hint, String key,
      {int maxLines = 1}) {
    final t = context.fw;
    return TextField(
      key: ValueKey(key),
      controller: c,
      enabled: !_busy,
      maxLines: maxLines,
      style: fwMono(t, size: 11.5, color: t.ink),
      decoration:
          InputDecoration(isDense: true, labelText: label, hintText: hint),
    );
  }

  Widget _resultBlock(FwTokens t, OperationResult result) {
    final doc = result.result;
    final verdict = '${doc['verdict'] ?? 'UNVERIFIABLE'}';
    final release = '${doc['release'] ?? 'HOLD'}';
    final exitCode = doc['cli_exit_code'];
    final status = verdict == 'PASS'
        ? 'verified'
        : verdict == 'FAIL'
            ? 'drift'
            : 'unverifiable';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        VerdictPill(verdict, status: status),
        const SizedBox(width: FwLayout.s2),
        VerdictPill(release,
            status: release == 'RELEASE' ? 'verified' : 'drift'),
        if (exitCode != null) ...[
          const SizedBox(width: FwLayout.s2),
          Text('exit $exitCode', style: fwMono(t, size: 11, color: t.inkFaint)),
        ],
      ]),
      const SizedBox(height: FwLayout.s2),
      HashText('operation', result.operationRef, keep: 20),
    ]);
  }
}

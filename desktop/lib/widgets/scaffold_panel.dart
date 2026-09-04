// scaffold_panel.dart -- seal a turn that happened somewhere else.
//
// Paste the prompt and the answer another tool produced. The engine freezes
// every source the prompt names, hashes both halves, and chains a turn
// receipt, so an answer from a model this app never called still arrives
// with provenance attached. Sources that could not be frozen are named with
// their reason; the panel shows those rather than a clean receipt.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'scaffold_strip.dart';

class ScaffoldPanel extends StatefulWidget {
  final GatewayClient client;
  const ScaffoldPanel({super.key, required this.client});

  @override
  State<ScaffoldPanel> createState() => _ScaffoldPanelState();
}

class _ScaffoldPanelState extends State<ScaffoldPanel> {
  final _prompt = TextEditingController();
  final _answer = TextEditingController();
  Map<String, dynamic>? _receipt;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _prompt.dispose();
    _answer.dispose();
    super.dispose();
  }

  Future<void> _seal() async {
    if (_busy) return;
    final prompt = _prompt.text.trim();
    final answer = _answer.text.trim();
    if (prompt.isEmpty && answer.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await widget.client.postJson('/api/scaffold',
          {'prompt': prompt, 'answer': answer},
          timeout: const Duration(seconds: 90));
      if (mounted) setState(() => _receipt = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('scaffold an outside turn'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Sources named in the prompt are frozen before the answer is '
              'hashed, so the receipt records what was actually available at '
              'the time rather than what a link says today.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _prompt,
            enabled: !_busy,
            maxLines: 3,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true,
                labelText: 'prompt',
                hintText: 'what was asked, links and all'),
          ),
          const SizedBox(height: FwLayout.s2),
          TextField(
            controller: _answer,
            enabled: !_busy,
            maxLines: 4,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true,
                labelText: 'answer',
                hintText: 'what the other tool replied'),
          ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy ? null : _seal,
            child: Text(_busy ? 'Freezing sources…' : 'Seal the turn'),
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The turn was not sealed: $_error'),
          ],
          if (_receipt != null) ...[
            const SizedBox(height: FwLayout.s3),
            _receiptBlock(t, _receipt!),
          ],
        ],
      ),
    );
  }

  Widget _receiptBlock(FwTokens t, Map<String, dynamic> r) {
    final scaffold = TurnScaffold.fromJson(r);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        HashText('prompt', '${r['prompt_sha256'] ?? ''}', keep: 16),
        const SizedBox(height: 4),
        HashText('answer', '${r['answer_sha256'] ?? ''}', keep: 16),
        if (scaffold.isEmpty)
          const Padding(
            padding: EdgeInsets.only(top: FwLayout.s3),
            child: HonestNull(
                'The prompt named no sources, so nothing was frozen. The two '
                'hashes above are the whole receipt.'),
          )
        else
          ScaffoldStrip(scaffold),
        if (r['not_frozen'] is List && (r['not_frozen'] as List).isNotEmpty)
          ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull(
              'Past the per-turn freeze budget, so named rather than '
              'frozen: ${(r['not_frozen'] as List).join(', ')}'),
        ],
        if (r['store_degraded'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull('The receipt was not stored: ${r['store_degraded']}'),
        ],
      ],
    );
  }
}

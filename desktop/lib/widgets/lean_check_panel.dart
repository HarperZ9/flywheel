// lean_check_panel.dart -- the kernel decides, and only the kernel.
//
// Paste Lean and the toolchain judges it. Three outcomes, and the third is
// the one that matters: passed true, passed false, or passed null, which
// means no toolchain was installed and the lane is DECLARED rather than
// live. A missing kernel is never rendered as a pass. Running the kernel is
// a subprocess and the verdict is stored, so it goes through the grant.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class LeanCheckPanel extends StatefulWidget {
  final GatewayClient client;
  const LeanCheckPanel({super.key, required this.client});

  @override
  State<LeanCheckPanel> createState() => _LeanCheckPanelState();
}

class _LeanCheckPanelState extends State<LeanCheckPanel> {
  final _code = TextEditingController();
  Map<String, dynamic>? _verdict;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _check() async {
    final code = _code.text.trim();
    if (code.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final requestId = 'lean-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'lean.check',
          clientRequestId: requestId,
          operation: {'code': code},
        ),
        (body) => widget.client.postJson('/api/lean', body,
            timeout: const Duration(minutes: 5)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _verdict = r);
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
          const Kicker('lean · the apex oracle', hot: true),
          const SizedBox(height: FwLayout.s1),
          Text(
              'A candidate carrying sorry or a smuggled axiom is refused '
              'before the kernel runs, because Lean exits zero on an '
              'admitted hole.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _code,
            enabled: !_busy,
            maxLines: 6,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true, labelText: 'lean source'),
          ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy ? null : _check,
            child: Text(_busy ? 'Asking the kernel…' : 'Ask the kernel'),
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The kernel was not reached: $_error'),
          ],
          if (_verdict != null) ...[
            const SizedBox(height: FwLayout.s3),
            _verdictBlock(t, _verdict!),
          ],
        ],
      ),
    );
  }

  Widget _verdictBlock(FwTokens t, Map<String, dynamic> v) {
    final passed = v['passed'];
    // A null verdict is DECLARED: no toolchain answered. It is neither a
    // pass nor a refusal, and collapsing it into either would be the lie
    // this whole panel exists to prevent.
    final label = passed == true
        ? 'KERNEL-ACCEPTED'
        : passed == false
            ? 'REFUSED'
            : 'DECLARED';
    final status = passed == true
        ? 'verified'
        : passed == false
            ? 'drift'
            : 'unverifiable';
    final toolchain = '${v['toolchain'] ?? ''}';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          VerdictPill(label, status: status),
          const SizedBox(width: FwLayout.s3),
          Text(toolchain.isEmpty ? 'no toolchain' : toolchain,
              style: fwMono(t, size: 11, color: t.inkFaint)),
        ]),
        const SizedBox(height: FwLayout.s2),
        HashText('code', '${v['code_sha256'] ?? ''}', keep: 16),
        const SizedBox(height: FwLayout.s2),
        SelectableText('${v['kernel_output'] ?? ''}',
            style: fwMono(t, size: 11, color: t.inkSoft)),
        if (v['note'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text('${v['note']}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ],
    );
  }
}

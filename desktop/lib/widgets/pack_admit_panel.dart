// pack_admit_panel.dart -- admit a domain pack, manifest first.
//
// A pack is admitted by its manifest, and the manifest is verified against
// the fixtures it names before anything is written. Admission persists to the
// run root and fires pack.admitted hooks, so it goes through the grant sheet.
// A hook that blocks the event is shown as a block, not folded into success.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class PackAdmitPanel extends StatefulWidget {
  final GatewayClient client;
  const PackAdmitPanel({super.key, required this.client});

  @override
  State<PackAdmitPanel> createState() => _PackAdmitPanelState();
}

class _PackAdmitPanelState extends State<PackAdmitPanel> {
  final _manifest = TextEditingController();
  final _fixtures = TextEditingController();
  Map<String, dynamic>? _ack;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _manifest.dispose();
    _fixtures.dispose();
    super.dispose();
  }

  Future<void> _admit() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final decoded = jsonDecode(_manifest.text.trim());
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('the manifest must be a JSON object');
      }
      final fixtures = _fixtures.text.trim();
      final requestId = 'packs-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'packs.admit',
          clientRequestId: requestId,
          operation: {
            'manifest': decoded,
            if (fixtures.isNotEmpty) 'fixtures_root': fixtures,
          },
        ),
        (body) => widget.client.postJson('/api/packs/admit', body,
            timeout: const Duration(seconds: 60)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _ack = r);
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
          const Kicker('admit a pack'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'The manifest is verified against the fixtures it names before '
              'the pack is written. A manifest that does not match its '
              'fixtures is refused, not admitted with a warning.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _manifest,
            enabled: !_busy,
            maxLines: 5,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true, labelText: 'manifest (JSON object)'),
          ),
          const SizedBox(height: FwLayout.s2),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _fixtures,
                enabled: !_busy,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true,
                    labelText: 'fixtures root',
                    hintText: 'blank = the current directory'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _admit,
              child: Text(_busy ? 'Verifying…' : 'Admit'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The pack was not admitted: $_error'),
          ],
          if (_ack != null) ...[
            const SizedBox(height: FwLayout.s3),
            _ackBlock(t, _ack!),
          ],
        ],
      ),
    );
  }

  Widget _ackBlock(FwTokens t, Map<String, dynamic> ack) {
    final blocked = ack['event_blocked'] == true;
    final receipts = ack['hook_receipts'] is List
        ? (ack['hook_receipts'] as List).length
        : 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          VerdictPill(blocked ? 'EVENT BLOCKED' : '${ack['state'] ?? 'admitted'}',
              status: blocked ? 'drift' : 'verified'),
          const SizedBox(width: FwLayout.s3),
          Text(
              '${ack['pack_id'] ?? ''} ${ack['version'] ?? ''}  ·  '
              '$receipts hook receipt(s)',
              style: fwMono(t, size: 11, color: t.inkFaint)),
        ]),
        const SizedBox(height: FwLayout.s2),
        HashText('pack', '${ack['pack_sha256'] ?? ''}', keep: 16),
        if (blocked) ...[
          const SizedBox(height: FwLayout.s2),
          const HonestNull(
              'A hook blocked the pack.admitted event. The pack is on disk; '
              'whatever the hook guards did not proceed.'),
        ],
      ],
    );
  }
}

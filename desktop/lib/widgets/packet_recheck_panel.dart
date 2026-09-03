// packet_recheck_panel.dart -- re-verify an exported evidence packet.
//
// The packet is the thing you hand to someone who does not trust you. This
// checks one on this machine: every byte rehashed, the criterion and journey
// re-derived, and, when an anchor digest is supplied, the manifest compared
// against it. DRIFT is a real answer and is rendered as one. So is
// UNVERIFIABLE, which says the packet could not be read well enough to
// judge, and is never softened into a pass.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class PacketRecheckPanel extends StatefulWidget {
  final GatewayClient client;
  const PacketRecheckPanel({super.key, required this.client});

  @override
  State<PacketRecheckPanel> createState() => _PacketRecheckPanelState();
}

class _PacketRecheckPanelState extends State<PacketRecheckPanel> {
  final _packet = TextEditingController();
  final _anchor = TextEditingController();
  Map<String, dynamic>? _result;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _packet.dispose();
    _anchor.dispose();
    super.dispose();
  }

  Future<void> _recheck() async {
    final packet = _packet.text.trim();
    if (packet.isEmpty || _busy) return;
    final anchor = _anchor.text.trim();
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      // A packet that fails to verify answers 422, and that answer is the
      // point: the body carries the verdict. Reading only 200s would turn
      // the finding the operator asked for into a transport error.
      final r = await widget.client
          .postJsonLenient('/api/evidence/recheck', {
        'packet_ref': packet,
        if (anchor.isNotEmpty) 'expected_manifest_sha256': anchor,
      }, timeout: const Duration(seconds: 60));
      if (mounted) setState(() => _result = r);
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
          const Kicker('recheck a packet'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Point this at an exported packet directory. Supply the anchor '
              'digest you were given separately and the manifest is compared '
              'against it, so a packet that was edited after export cannot '
              'pass by carrying its own hash.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _packet,
            enabled: !_busy,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true,
                labelText: 'packet directory',
                hintText: 'a path under the run root'),
          ),
          const SizedBox(height: FwLayout.s2),
          TextField(
            controller: _anchor,
            enabled: !_busy,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true,
                labelText: 'anchor digest (optional)',
                hintText: 'sha256:…'),
          ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy ? null : _recheck,
            child: Text(_busy ? 'Rechecking…' : 'Recheck'),
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The recheck could not run: $_error'),
          ],
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s3),
            _verdict(t, _result!),
          ],
        ],
      ),
    );
  }

  Widget _verdict(FwTokens t, Map<String, dynamic> r) {
    final verdict = '${r['verdict'] ?? 'UNVERIFIABLE'}';
    final parts = <String, String>{
      'structural': '${r['structural_verdict'] ?? ''}',
      'authenticity': '${r['authenticity_verdict'] ?? ''}',
      'rehash resistance': '${r['rehash_resistance_verdict'] ?? ''}',
    }..removeWhere((_, value) => value.isEmpty);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        VerdictPill(verdict, status: _status(verdict)),
        if (parts.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Wrap(
            spacing: FwLayout.s2,
            runSpacing: FwLayout.s2,
            children: [
              for (final entry in parts.entries)
                VerdictPill('${entry.key} · ${entry.value}',
                    status: _status(entry.value)),
            ],
          ),
        ],
        if (r['packet_sha256'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          HashText('manifest', '${r['packet_sha256']}', keep: 20),
        ],
        if (_detail(r) != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull(_detail(r)!),
        ],
      ],
    );
  }

  /// The transport refuses in its own shape: {error: {code, message}}.
  /// Rendering only `detail` would leave a refusal with nothing on screen
  /// but a bare UNVERIFIABLE chip and no reason for it.
  String? _detail(Map<String, dynamic> r) {
    final detail = r['detail'];
    if (detail is String && detail.isNotEmpty) return detail;
    final error = r['error'];
    if (error is Map) return '${error['code']}: ${error['message']}';
    if (error is String && error.isNotEmpty) return error;
    return null;
  }

  /// MATCH is the only pass. DRIFT is a finding, and anything else is a
  /// refusal to decide, which the neutral mark states rather than hides.
  String _status(String verdict) => switch (verdict) {
        'MATCH' => 'verified',
        'DRIFT' => 'drift',
        _ => 'unverifiable',
      };
}

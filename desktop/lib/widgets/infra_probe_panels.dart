// infra_probe_panels.dart -- the two probes that go through a grant.
//
// A credential scan reads the files and environment where secrets live. It
// records a type, a location, and a non-reversible fingerprint, and never a
// value, so nothing on this surface is a secret. An isolation probe leaves
// the machine on purpose to find out which boundaries actually hold. One
// reads credential-shaped material and the other reaches the network, so
// neither is a plain button.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

Map<String, dynamic> _sealBody(Map<String, dynamic> receipt) =>
    (receipt['seal_body'] as Map?)?.cast<String, dynamic>() ?? {};

Iterable<Map<String, dynamic>> _rows(Object? raw) => raw is List
    ? raw.whereType<Map>().map((m) => m.cast<String, dynamic>())
    : const <Map<String, dynamic>>[];

class CredentialScanPanel extends StatefulWidget {
  final GatewayClient client;
  const CredentialScanPanel({super.key, required this.client});

  @override
  State<CredentialScanPanel> createState() => _CredentialScanPanelState();
}

class _CredentialScanPanelState extends State<CredentialScanPanel> {
  final _root = TextEditingController();
  Map<String, dynamic>? _receipt;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _root.dispose();
    super.dispose();
  }

  Future<void> _scan() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final root = _root.text.trim();
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'infra.credential_scan',
          clientRequestId: 'credscan-${DateTime.now().microsecondsSinceEpoch}',
          // An empty root is omitted rather than sent blank: the scan then
          // reads the environment, which is a different request and not a
          // degenerate one.
          operation: root.isEmpty ? const {} : {'root': root},
        ),
        (body) => widget.client.postJson('/api/infra/credential-scan', body,
            timeout: const Duration(minutes: 3)),
        currentOperation: () => null,
      );
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
    final body = _receipt == null ? null : _sealBody(_receipt!);
    final count = body == null ? 0 : (body['finding_count'] ?? 0);
    final scanned = body == null ? '' : '${body['scan_root'] ?? ''}';
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('credential scan · presence, never value'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Finds credential-shaped material in the environment and, when '
              'a root is given, on disk beneath it. What comes back is a '
              'type, a location, and a fingerprint nobody can reverse.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _root,
            enabled: !_busy,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true,
                labelText: 'root to walk (blank reads the environment only)'),
          ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy ? null : _scan,
            child: Text(_busy ? 'Scanning…' : 'Scan for credentials'),
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The scan did not run: $_error'),
          ],
          if (body != null) ...[
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              VerdictPill('$count FOUND',
                  status: count == 0 ? 'verified' : 'drift'),
              const SizedBox(width: FwLayout.s3),
              Text(scanned.isEmpty ? 'environment only' : scanned,
                  style: fwMono(t, size: 11, color: t.inkFaint)),
            ]),
            const SizedBox(height: FwLayout.s2),
            for (final f in _rows(body['findings']))
              Text(
                  '${f['secret_type'] ?? '?'} at ${f['location'] ?? '?'} · '
                  'fingerprint ${f['fingerprint'] ?? '?'}',
                  style: fwMono(t, size: 11, color: t.inkSoft)),
            const SizedBox(height: FwLayout.s2),
            HashText('seal', '${_receipt!['seal_hash'] ?? ''}', keep: 24),
          ],
        ],
      ),
    );
  }
}

class IsolationProbePanel extends StatefulWidget {
  final GatewayClient client;
  const IsolationProbePanel({super.key, required this.client});

  @override
  State<IsolationProbePanel> createState() => _IsolationProbePanelState();
}

class _IsolationProbePanelState extends State<IsolationProbePanel> {
  Map<String, dynamic>? _receipt;
  String? _error;
  bool _busy = false;

  Future<void> _probe() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'infra.isolation',
          clientRequestId:
              'isolation-${DateTime.now().microsecondsSinceEpoch}',
          operation: const {},
        ),
        (body) => widget.client.postJson('/api/infra/isolation', body,
            timeout: const Duration(minutes: 2)),
        currentOperation: () => null,
      );
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
    final body = _receipt == null ? null : _sealBody(_receipt!);
    final overall = '${body?['overall_verdict'] ?? ''}';
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('isolation probe · which boundaries hold'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Reaches for the cloud metadata endpoint, an inherited cloud '
              'identity, a package registry, the filesystem outside the run, '
              'and public DNS. Reachable is a finding, and it stays visible.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy ? null : _probe,
            child: Text(_busy ? 'Probing…' : 'Probe the boundary'),
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The probe did not run: $_error'),
          ],
          if (body != null) ...[
            const SizedBox(height: FwLayout.s3),
            VerdictPill(overall.isEmpty ? 'UNVERIFIABLE' : overall,
                status: overall == 'VERIFIED' ? 'verified' : 'drift'),
            const SizedBox(height: FwLayout.s2),
            for (final test in _rows(body['tests'])) _test(t, test),
            const SizedBox(height: FwLayout.s2),
            HashText('seal', '${_receipt!['seal_hash'] ?? ''}', keep: 24),
          ],
        ],
      ),
    );
  }

  Widget _test(FwTokens t, Map<String, dynamic> test) {
    final result = '${test['result'] ?? ''}';
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s1),
      child: Row(children: [
        VerdictPill(result.toUpperCase(),
            status: result == 'blocked' ? 'verified' : 'drift'),
        const SizedBox(width: FwLayout.s3),
        Flexible(
          child: Text(
              '${test['boundary'] ?? ''} · ${test['test'] ?? ''} · '
              '${test['detail'] ?? ''}',
              maxLines: 2,
              style: fwMono(t, size: 11, color: t.inkSoft)),
        ),
      ]),
    );
  }
}

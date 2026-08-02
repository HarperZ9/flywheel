// governance_view.dart -- the TADR governance surface: tier assignments,
// control baseline compliance, and pause triggers.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class GovernanceView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const GovernanceView({super.key, required this.client, required this.alive});

  @override
  State<GovernanceView> createState() => _GovernanceViewState();
}

class _GovernanceViewState extends State<GovernanceView> {
  Map<String, dynamic>? _tiers;
  Map<String, dynamic>? _compliance;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(GovernanceView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive || _loading) return;
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        widget.client.getJson('/api/governance/tiers'),
        widget.client.getJson('/api/governance/compliance'),
      ]);
      if (mounted) {
        setState(() {
          _tiers = results[0];
          _compliance = results[1];
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Governance appears when it runs.',
          command: 'flywheel up');
    }
    if (_error != null) return FwEmpty('Governance unavailable: $_error');
    if (_tiers == null) {
      return const Center(
          child: SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2)));
    }
    return ViewScroll(
      children: [
        const SectionHeader('Governance',
            kicker: 'TADR tier system and control baselines'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'The Tiered All-Hazards Defensive Risk Manual as machine-enforced '
          'governance. Every system is classified T1 (localized), T2 (severe/'
          'scalable), or T3 (catastrophic/irreversible). Control baselines '
          'scale with the tier.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        _TierDefinitions(tiers: _tiers!),
        const SizedBox(height: FwLayout.s4),
        if (_compliance != null) _ComplianceReport(report: _compliance!),
      ],
    );
  }
}

class _TierDefinitions extends StatelessWidget {
  final Map<String, dynamic> tiers;
  const _TierDefinitions({required this.tiers});

  @override
  Widget build(BuildContext context) {
    final tierMap = tiers['tiers'] as Map<String, dynamic>? ?? {};
    final modifiers = tiers['modifiers'] as List? ?? [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('tier definitions'),
        const SizedBox(height: FwLayout.s2),
        for (final entry in tierMap.entries)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s2),
            child: HairlineCard(
              child: Row(children: [
                Text(entry.key,
                    style: fwMono(context.fw, size: 16)
                        .copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(width: FwLayout.s3),
                Expanded(
                  child: Text(_tierDescription(entry.key),
                      style: Theme.of(context).textTheme.bodySmall),
                ),
              ]),
            ),
          ),
        if (modifiers.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text('Modifiers: ${modifiers.join(", ")}',
              style: fwMono(context.fw, size: 11)
                  .copyWith(color: context.fw.inkFaint)),
        ],
      ],
    );
  }

  String _tierDescription(String tier) {
    switch (tier) {
      case 'T1':
        return 'Controlled and localized risk';
      case 'T2':
        return 'Severe, scalable, or cross-system risk';
      case 'T3':
        return 'Catastrophic, strategic, or irreversible risk';
      default:
        return '';
    }
  }
}

class _ComplianceReport extends StatelessWidget {
  final Map<String, dynamic> report;
  const _ComplianceReport({required this.report});

  @override
  Widget build(BuildContext context) {
    final tier = report['tier'] ?? 'unknown';
    final checked = report['checked'] ?? 0;
    final passed = report['passed'] ?? 0;
    final failed = report['failed'] ?? 0;
    final compliant = report['compliant'] ?? false;
    final checks = (report['checks'] as List? ?? [])
        .whereType<Map<String, dynamic>>()
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('control baseline compliance'),
        const SizedBox(height: FwLayout.s2),
        HairlineCard(
          child: Row(children: [
            Text('Tier $tier',
                style: fwMono(context.fw, size: 14)
                    .copyWith(fontWeight: FontWeight.w600)),
            const Spacer(),
            VerdictPill(
                compliant ? 'compliant' : '$failed missing',
                status: compliant ? 'verified' : 'drift'),
          ]),
        ),
        const SizedBox(height: FwLayout.s2),
        Text('$passed of $checked controls present',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: FwLayout.s3),
        for (final check in checks.take(10))
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s2),
            child: Row(children: [
              Icon(
                check['present'] == true
                    ? Icons.check_circle_outline
                    : Icons.error_outline,
                size: 14,
                color: check['present'] == true
                    ? Theme.of(context).colorScheme.outline
                    : Theme.of(context).colorScheme.error,
              ),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Text('${check["name"]}',
                    style: Theme.of(context).textTheme.bodySmall),
              ),
            ]),
          ),
        if (checks.length > 10)
          Text('+ ${checks.length - 10} more...',
              style: fwMono(context.fw, size: 11)
                  .copyWith(color: context.fw.inkFaint)),
      ],
    );
  }
}

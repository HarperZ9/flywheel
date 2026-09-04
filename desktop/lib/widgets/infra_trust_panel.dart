// infra_trust_panel.dart -- the trust model and the run bill of materials.
//
// The trust model names what enforces each safety claim and which single
// components would take the whole architecture down alone. The engine
// compares its declared list against the one its components imply, so this
// panel renders that answer rather than reaching a second one.
//
// The bill of materials is the run's identity: model, runtime, tool scopes,
// which credentials were present, and any safeguard that was removed. It
// carries its own seal, which is what makes it re-checkable later.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

List<Map<String, dynamic>> _maps(Object? raw) => raw is List
    ? raw.whereType<Map>().map((m) => m.cast<String, dynamic>()).toList()
    : const [];

List<String> _strings(Object? raw) =>
    raw is List ? raw.map((v) => '$v').toList() : const [];

class TrustModelPanel extends StatelessWidget {
  final Map<String, dynamic>? model;
  const TrustModelPanel({super.key, this.model});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final m = model;
    if (m == null) {
      return const HairlineCard(
          child: HonestNull('The trust model has not been read yet.'));
    }
    final components = _maps(m['components']);
    final claims = _maps(m['safety_claims']);
    final declared = _strings(m['single_points_of_failure']);
    final derived = _strings(m['derived_single_points_of_failure']);
    final errors = _strings(m['validation_errors']);
    final agrees = m['single_point_agreement'] == true;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('trust model · what enforces what', hot: true),
          const SizedBox(height: FwLayout.s1),
          Text('${m['description'] ?? ''}',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          AdaptiveTiles(children: [
            StatTile(label: 'components', value: '${components.length}'),
            StatTile(label: 'safety claims', value: '${claims.length}'),
            StatTile(
                label: 'single points',
                value: '${derived.length}',
                status: derived.isEmpty ? 'verified' : 'drift'),
          ]),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            VerdictPill(agrees ? 'DECLARED MATCHES DERIVED' : 'LISTS DIVERGE',
                status: agrees ? 'verified' : 'drift'),
          ]),
          const SizedBox(height: FwLayout.s2),
          Text('declared: ${declared.isEmpty ? 'none' : declared.join(', ')}',
              style: fwMono(t, size: 11, color: t.inkSoft)),
          Text('derived: ${derived.isEmpty ? 'none' : derived.join(', ')}',
              style: fwMono(t, size: 11, color: t.inkSoft)),
          if (errors.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The model does not validate: ${errors.join('; ')}'),
          ],
          const SizedBox(height: FwLayout.s4),
          const Kicker('claims and their failure modes'),
          const SizedBox(height: FwLayout.s2),
          for (final c in claims) _claim(t, c),
          const SizedBox(height: FwLayout.s3),
          const Kicker('adversary paths'),
          const SizedBox(height: FwLayout.s2),
          for (final path in _strings(m['adversary_paths']))
            Padding(
              padding: const EdgeInsets.only(bottom: FwLayout.s1),
              child:
                  Text(path, style: fwMono(t, size: 11, color: t.inkSoft)),
            ),
        ],
      ),
    );
  }

  Widget _claim(FwTokens t, Map<String, dynamic> c) {
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${c['claim_id'] ?? ''}  ${c['statement'] ?? ''}',
              style: TextStyle(fontSize: 12.5, color: t.ink)),
          Text(
              'enforced by ${c['enforcement_component'] ?? 'nothing named'} · '
              'confidence ${c['confidence'] ?? 'unstated'} · '
              'fails when ${c['failure_mode'] ?? 'unstated'}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ),
    );
  }
}

class RunBomPanel extends StatelessWidget {
  final Map<String, dynamic>? bom;
  const RunBomPanel({super.key, this.bom});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final b = bom;
    if (b == null) {
      return const HairlineCard(
          child: HonestNull('The bill of materials has not been read yet.'));
    }
    final runtime = (b['runtime'] as Map?)?.cast<String, dynamic>() ?? {};
    final model = (b['model'] as Map?)?.cast<String, dynamic>() ?? {};
    final tools = (b['tools'] as Map?)?.cast<String, dynamic>() ?? {};
    final scopes = (tools['scopes'] as Map?)?.cast<String, dynamic>() ?? {};
    final present = _strings(b['credentials_present']);
    final removed = _strings(b['safeguards_removed']);
    final named = '${model['name'] ?? ''}';
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('run bill of materials'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'What this run is made of. The seal is over the whole list, so '
              'a later reader can check that none of it moved.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Text(
              'python ${runtime['python_version'] ?? '?'} · harness '
              '${runtime['harness_version'] ?? '?'}',
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
          Text('model: ${named.isEmpty ? 'none recorded' : named}',
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
          Text('tools under scope: ${scopes.length}',
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
          const SizedBox(height: FwLayout.s2),
          // Presence, never a value. The list names which credentials the run
          // could see; no secret ever reaches this surface.
          Text(
              present.isEmpty
                  ? 'credentials present: none'
                  : 'credentials present: ${present.join(', ')}',
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
          const SizedBox(height: FwLayout.s3),
          if (removed.isEmpty)
            Row(children: const [
              VerdictPill('NO SAFEGUARD REMOVED', status: 'verified')
            ])
          else
            HonestNull('Safeguards removed: ${removed.join(', ')}'),
          const SizedBox(height: FwLayout.s3),
          HashText('seal', '${b['seal_hash'] ?? ''}', keep: 24),
        ],
      ),
    );
  }
}

// Five stable destination groups. Labels are presentation;
// DestinationId remains the routing contract when a label changes.
import '../assistant/assistant_identity.dart';
import 'app_route.dart';

enum DestinationGroup { work, chat, code, evidence, advanced }

class DestinationSpec {
  final DestinationId id;
  final String label;
  final String abbr;
  final DestinationGroup group;

  /// Phone primary destinations appear in the bottom bar; the rest are in More.
  final bool mobilePrimary;
  const DestinationSpec(
    this.id,
    this.label, {
    required this.abbr,
    required this.group,
    this.mobilePrimary = false,
  });
}

const destinationCatalog = <DestinationSpec>[
  DestinationSpec(
    DestinationId.journey,
    'Journey',
    abbr: 'JN',
    group: DestinationGroup.work,
    mobilePrimary: true,
  ),
  DestinationSpec(
    DestinationId.plan,
    'Plan',
    abbr: 'PN',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.workflows,
    'Workflows',
    abbr: 'WF',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.projects,
    'Projects',
    abbr: 'PR',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.writing,
    'Writing',
    abbr: 'WR',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.swarms,
    'Swarms',
    abbr: 'SW',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.roadmap,
    'Roadmap',
    abbr: 'RM',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.schedule,
    'Schedule',
    abbr: 'SD',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.runners,
    'Runners',
    abbr: 'RN',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.approvals,
    'Approvals',
    abbr: 'AP',
    group: DestinationGroup.work,
    mobilePrimary: true,
  ),
  DestinationSpec(
    DestinationId.bulletin,
    'Bulletin',
    abbr: 'BL',
    group: DestinationGroup.work,
  ),
  DestinationSpec(
    DestinationId.chat,
    AssistantIdentity.name,
    abbr: AssistantIdentity.abbreviation,
    group: DestinationGroup.chat,
    mobilePrimary: true,
  ),
  DestinationSpec(
    DestinationId.compare,
    'Compare',
    abbr: 'CP',
    group: DestinationGroup.chat,
  ),
  DestinationSpec(
    DestinationId.models,
    'Models',
    abbr: 'MD',
    group: DestinationGroup.chat,
  ),
  DestinationSpec(
    DestinationId.companion,
    'Companion',
    abbr: 'CN',
    group: DestinationGroup.chat,
    mobilePrimary: true,
  ),
  DestinationSpec(
    DestinationId.code,
    'Code',
    abbr: 'CO',
    group: DestinationGroup.code,
  ),
  DestinationSpec(
    DestinationId.eval,
    'Eval',
    abbr: 'EV',
    group: DestinationGroup.code,
  ),
  DestinationSpec(
    DestinationId.audit,
    'Audit',
    abbr: 'AU',
    group: DestinationGroup.code,
  ),
  DestinationSpec(
    DestinationId.lint,
    'Lint',
    abbr: 'LT',
    group: DestinationGroup.code,
  ),
  DestinationSpec(
    DestinationId.scan,
    'Scan',
    abbr: 'SN',
    group: DestinationGroup.code,
  ),
  DestinationSpec(
    DestinationId.receipts,
    'Receipts',
    abbr: 'RC',
    group: DestinationGroup.evidence,
    mobilePrimary: true,
  ),
  DestinationSpec(
    DestinationId.science,
    'Science',
    abbr: 'SC',
    group: DestinationGroup.evidence,
  ),
  DestinationSpec(
    DestinationId.world,
    'World',
    abbr: 'WD',
    group: DestinationGroup.evidence,
  ),
  DestinationSpec(
    DestinationId.memory,
    'Memory',
    abbr: 'ME',
    group: DestinationGroup.evidence,
  ),
  DestinationSpec(
    DestinationId.governance,
    'Governance',
    abbr: 'GV',
    group: DestinationGroup.evidence,
  ),
  DestinationSpec(
    DestinationId.usage,
    'Usage',
    abbr: 'US',
    group: DestinationGroup.evidence,
  ),
  DestinationSpec(
    DestinationId.infra,
    'Infra',
    abbr: 'IF',
    group: DestinationGroup.evidence,
  ),
  DestinationSpec(
    DestinationId.studio,
    'Studio',
    abbr: 'ST',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.graph,
    'Graph',
    abbr: 'GR',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.feeds,
    'Feeds',
    abbr: 'FD',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.discourse,
    'Discourse',
    abbr: 'DS',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.academy,
    'Academy',
    abbr: 'AY',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.lessons,
    'Lessons',
    abbr: 'LE',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.instruments,
    'Instruments',
    abbr: 'IS',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.browser,
    'Browser',
    abbr: 'BR',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.lanes,
    'Tools',
    abbr: 'TL',
    group: DestinationGroup.evidence,
  ),
  DestinationSpec(
    DestinationId.forum,
    'Forum',
    abbr: 'FM',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.registry,
    'Registry',
    abbr: 'RG',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.relay,
    'Relay',
    abbr: 'RL',
    group: DestinationGroup.code,
  ),
  DestinationSpec(
    DestinationId.train,
    'Train',
    abbr: 'TR',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.uplift,
    'Uplift',
    abbr: 'UP',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.family,
    'Family',
    abbr: 'FA',
    group: DestinationGroup.advanced,
  ),
  DestinationSpec(
    DestinationId.plugins,
    'Plugins',
    abbr: 'PL',
    group: DestinationGroup.advanced,
  ),
];

DestinationSpec? specFor(DestinationId id) {
  for (final spec in destinationCatalog) {
    if (spec.id == id) return spec;
  }
  return null;
}

/// Bottom-bar destinations in catalog order, followed by More for the full set.
final List<DestinationSpec> mobilePrimaryDestinations =
    destinationCatalog.where((spec) => spec.mobilePrimary).toList();

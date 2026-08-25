// destination_catalog.dart -- the frozen 30-destination map.
//
// Five stable groups, exactly as the completion spec fixes them. Labels
// are presentation; the DestinationId is the contract, so a label can be
// renamed without a single route changing.
import 'app_route.dart';

enum DestinationGroup { work, chat, code, evidence, advanced }

class DestinationSpec {
  final DestinationId id;
  final String label;
  final String abbr;
  final DestinationGroup group;
  const DestinationSpec(this.id, this.label,
      {required this.abbr, required this.group});
}

const destinationCatalog = <DestinationSpec>[
  DestinationSpec(DestinationId.journey, 'Journey',
      abbr: 'JN', group: DestinationGroup.work),
  DestinationSpec(DestinationId.plan, 'Plan',
      abbr: 'PN', group: DestinationGroup.work),
  DestinationSpec(DestinationId.workflows, 'Workflows',
      abbr: 'WF', group: DestinationGroup.work),
  DestinationSpec(DestinationId.projects, 'Projects',
      abbr: 'PR', group: DestinationGroup.work),

  DestinationSpec(DestinationId.swarms, 'Swarms',
      abbr: 'SW', group: DestinationGroup.work),

  DestinationSpec(DestinationId.roadmap, 'Roadmap',
      abbr: 'RM', group: DestinationGroup.work),
  DestinationSpec(DestinationId.chat, 'Chat',
      abbr: 'CH', group: DestinationGroup.chat),
  DestinationSpec(DestinationId.compare, 'Compare',
      abbr: 'CP', group: DestinationGroup.chat),
  DestinationSpec(DestinationId.models, 'Models',
      abbr: 'MD', group: DestinationGroup.chat),
  DestinationSpec(DestinationId.companion, 'Companion',
      abbr: 'CN', group: DestinationGroup.chat),
  DestinationSpec(DestinationId.code, 'Code',
      abbr: 'CO', group: DestinationGroup.code),
  DestinationSpec(DestinationId.eval, 'Eval',
      abbr: 'EV', group: DestinationGroup.code),
  DestinationSpec(DestinationId.audit, 'Audit',
      abbr: 'AU', group: DestinationGroup.code),
  DestinationSpec(DestinationId.lint, 'Lint',
      abbr: 'LT', group: DestinationGroup.code),
  DestinationSpec(DestinationId.receipts, 'Receipts',
      abbr: 'RC', group: DestinationGroup.evidence),
  DestinationSpec(DestinationId.science, 'Science',
      abbr: 'SC', group: DestinationGroup.evidence),
  DestinationSpec(DestinationId.world, 'World',
      abbr: 'WD', group: DestinationGroup.evidence),
  DestinationSpec(DestinationId.memory, 'Memory',
      abbr: 'ME', group: DestinationGroup.evidence),
  DestinationSpec(DestinationId.governance, 'Governance',
      abbr: 'GV', group: DestinationGroup.evidence),
  DestinationSpec(DestinationId.usage, 'Usage',
      abbr: 'US', group: DestinationGroup.evidence),
  DestinationSpec(DestinationId.studio, 'Studio',
      abbr: 'ST', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.graph, 'Graph',
      abbr: 'GR', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.feeds, 'Feeds',
      abbr: 'FD', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.discourse, 'Discourse',
      abbr: 'DS', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.academy, 'Academy',
      abbr: 'AY', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.lessons, 'Lessons',
      abbr: 'LE', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.instruments, 'Instruments',
      abbr: 'IS', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.lanes, 'Lanes',
      abbr: 'LN', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.train, 'Train',
      abbr: 'TR', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.uplift, 'Uplift',
      abbr: 'UP', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.family, 'Family',
      abbr: 'FA', group: DestinationGroup.advanced),
  DestinationSpec(DestinationId.plugins, 'Plugins',
      abbr: 'PL', group: DestinationGroup.advanced),
];

DestinationSpec? specFor(DestinationId id) {
  for (final spec in destinationCatalog) {
    if (spec.id == id) return spec;
  }
  return null;
}

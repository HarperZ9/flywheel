// Which destinations exist, in the order the rail renders them inside each
// group. The spec type and the group enum live in destination_spec.dart and
// are re-exported here.
import '../assistant/assistant_identity.dart';
import 'app_route.dart';
import 'destination_catalog_advanced.dart';
import 'destination_spec.dart';

export 'destination_spec.dart';

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
    DestinationId.relay,
    'Relay',
    abbr: 'RL',
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
    DestinationId.lanes,
    'Tools',
    abbr: 'TL',
    group: DestinationGroup.evidence,
  ),
  ...advancedDestinations,
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

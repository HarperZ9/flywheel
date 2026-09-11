import 'app_route.dart';
import 'destination_catalog.dart';

String destinationGroupLabel(DestinationGroup group) => switch (group) {
      DestinationGroup.work => 'Start & run',
      DestinationGroup.chat => 'Chat & models',
      DestinationGroup.code => 'Code & checks',
      DestinationGroup.evidence => 'Proof & state',
      DestinationGroup.advanced => 'Tools & admin',
    };

bool destinationMatches(DestinationSpec spec, String query) {
  final terms = query.trim().toLowerCase().split(RegExp(r'\s+'));
  if (terms.length == 1 && terms.single.isEmpty) return true;
  final text = destinationSearchText(spec).toLowerCase();
  return terms.every(text.contains);
}

String destinationSearchText(DestinationSpec spec) => [
      spec.label,
      spec.abbr,
      spec.group.name,
      destinationGroupLabel(spec.group),
      ..._keywords(spec.id),
    ].join(' ');

List<String> _keywords(DestinationId id) => switch (id) {
      DestinationId.journey => ['start', 'resume', 'recover', 'first run'],
      DestinationId.plan => ['task', 'approve', 'workflow', 'run'],
      DestinationId.workflows => ['task', 'run', 'pipeline'],
      DestinationId.projects => ['workspace', 'folder', 'register'],
      DestinationId.bulletin => ['board', 'publish', 'public', 'lane'],
      DestinationId.approvals => ['permission', 'grant', 'review'],
      DestinationId.chat => ['ask', 'prompt', 'agent', 'assistant'],
      DestinationId.models => ['setup', 'connect', 'sign in', 'endpoint'],
      DestinationId.code => ['workspace', 'agent', 'edit', 'files'],
      DestinationId.receipts => ['proof', 'evidence', 'verify', 'ledger'],
      DestinationId.relay => ['phone', 'remote', 'gateway'],
      DestinationId.lanes => [
          'lanes',
          'installed',
          'setup',
          'health',
          'probe',
          'readiness',
          'repair',
          'mcp',
          'capabilities',
          'callable',
        ],
      DestinationId.plugins => ['tools', 'mcp', 'marketplace'],
      DestinationId.infra => ['engine', 'gateway', 'health'],
      _ => const [],
    };

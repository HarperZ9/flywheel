// The advanced group's data. It lives beside the catalog rather than in it
// so the file that defines the group enum, the spec and the lookups stays
// readable as one screen of mechanism. Order inside the group is the order
// the rail renders; the group itself is placed by the catalog.
import 'app_route.dart';
import 'destination_spec.dart';

const advancedDestinations = <DestinationSpec>[
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
  DestinationSpec(
    DestinationId.peers,
    'Peers',
    abbr: 'PS',
    group: DestinationGroup.advanced,
  ),
];

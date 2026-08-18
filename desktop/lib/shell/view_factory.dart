import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../controllers/journey_controller.dart';
import '../ide/code_buffer_session.dart';
import '../ide/unsaved_work_guard.dart';
import '../models/gateway_models.dart';
import '../services/settings.dart';
import '../views/academy_view.dart';
import '../views/agent_view.dart';
import '../views/audit_view.dart';
import '../views/code_view.dart';
import '../views/compare_view.dart';
import '../views/companion_view.dart';
import '../views/discourse_view.dart';
import '../views/endpoints_view.dart';
import '../views/eval_view.dart';
import '../views/family_view.dart';
import '../views/feeds_view.dart';
import '../views/governance_view.dart';
import '../views/graph_view.dart';
import '../views/instruments_view.dart';
import '../views/journey_view.dart';
import '../views/lanes_view.dart';
import '../views/lessons_view.dart';
import '../views/lint_view.dart';
import '../views/memory_view.dart';
import '../views/plan_view.dart';
import '../views/plugins_view.dart';
import '../views/projects_view.dart';
import '../views/receipts_view.dart';
import '../views/science_view.dart';
import '../views/studio_view.dart';
import '../views/train_view.dart';
import '../views/uplift_view.dart';
import '../views/usage_view.dart';
import '../views/workflows_view.dart';
import '../views/world_view.dart';
import '../widgets/fw.dart';
import '../widgets/side_rail.dart';

const flywheelDestinations = <RailDestination>[
  RailDestination('Journey', abbr: 'JN', group: 'Start'),
  RailDestination('Chat', abbr: 'CH', group: 'Start'),
  RailDestination('Compare', abbr: 'CP', group: 'Start'),
  RailDestination('Models', abbr: 'MD', group: 'Start'),
  RailDestination('Code', abbr: 'CO', group: 'Do'),
  RailDestination('Eval', abbr: 'EV', group: 'Do'),
  RailDestination('Audit', abbr: 'AU', group: 'Do'),
  RailDestination('Companion', abbr: 'CN', group: 'Do'),
  RailDestination('Plan', abbr: 'PN', group: 'Do'),
  RailDestination('Workflows', abbr: 'WF', group: 'Do'),
  RailDestination('Studio', abbr: 'ST', group: 'Do'),
  RailDestination('Lint', abbr: 'LT', group: 'Do'),
  RailDestination('Memory', abbr: 'ME', group: 'Know'),
  RailDestination('Graph', abbr: 'GR', group: 'Know'),
  RailDestination('Projects', abbr: 'PR', group: 'Know'),
  RailDestination('Feeds', abbr: 'FD', group: 'Know'),
  RailDestination('Discourse', abbr: 'DS', group: 'Know'),
  RailDestination('Academy', abbr: 'AY', group: 'Know'),
  RailDestination('Lessons', abbr: 'LE', group: 'Know'),
  RailDestination('Governance', abbr: 'GV', group: 'Know'),
  RailDestination('Receipts', abbr: 'RC', group: 'Advanced'),
  RailDestination('Usage', abbr: 'US', group: 'Advanced'),
  RailDestination('Instruments', abbr: 'IS', group: 'Advanced'),
  RailDestination('Science', abbr: 'SC', group: 'Advanced'),
  RailDestination('World', abbr: 'WD', group: 'Advanced'),
  RailDestination('Lanes', abbr: 'LN', group: 'Advanced'),
  RailDestination('Train', abbr: 'TR', group: 'Advanced'),
  RailDestination('Uplift', abbr: 'UP', group: 'Advanced'),
  RailDestination('Family', abbr: 'FA', group: 'Advanced'),
  RailDestination('Plugins', abbr: 'PL', group: 'Advanced'),
];

final class DestinationInputs {
  const DestinationInputs({
    required this.client,
    required this.journey,
    required this.code,
    required this.codeGuard,
    required this.alive,
    required this.settings,
    required this.onProbe,
    required this.onInstall,
    this.pendingArgument,
    this.roster,
    this.world,
  });

  final GatewayClient client;
  final JourneyController journey;
  final CodeBufferSession code;
  final UnsavedWorkGuard codeGuard;
  final bool alive;
  final DesktopSettings settings;
  final Object? pendingArgument;
  final LaneRoster? roster;
  final WorldDoc? world;
  final VoidCallback onProbe;
  final Future<Map<String, dynamic>> Function(String) onInstall;
}

Widget buildDestinationView(String label, DestinationInputs input) =>
    _startAndDo(label, input) ??
    _knowledge(label, input) ??
    _advanced(label, input) ??
    const FwEmpty('Unknown view');

Widget? _startAndDo(String label, DestinationInputs i) => switch (label) {
      'Journey' => JourneyView(controller: i.journey),
      'Chat' =>
        AgentView(client: i.client, alive: i.alive, settings: i.settings),
      'Compare' =>
        CompareView(client: i.client, alive: i.alive, settings: i.settings),
      'Models' => EndpointsView(client: i.client, alive: i.alive),
      'Code' => CodeView(
          client: i.client,
          alive: i.alive,
          settings: i.settings,
          session: i.code,
          guard: i.codeGuard),
      'Eval' => EvalView(client: i.client, alive: i.alive),
      'Audit' => AuditView(client: i.client, alive: i.alive),
      'Companion' => CompanionView(client: i.client, alive: i.alive),
      'Plan' =>
        PlanView(client: i.client, alive: i.alive, settings: i.settings),
      'Workflows' =>
        WorkflowsView(client: i.client, alive: i.alive, settings: i.settings),
      'Studio' => StudioView(
          world: i.world, roster: i.roster, alive: i.alive, client: i.client),
      'Lint' => LintView(client: i.client, alive: i.alive),
      _ => null,
    };

Widget? _knowledge(String label, DestinationInputs i) => switch (label) {
      'Memory' => MemoryView(client: i.client, alive: i.alive),
      'Graph' => GraphView(client: i.client, alive: i.alive),
      'Projects' => ProjectsView(client: i.client, alive: i.alive),
      'Feeds' => FeedsView(client: i.client, alive: i.alive),
      'Discourse' =>
        DiscourseView(client: i.client, alive: i.alive, settings: i.settings),
      'Academy' => AcademyView(client: i.client, alive: i.alive),
      'Lessons' => LessonsView(client: i.client, alive: i.alive),
      'Governance' => GovernanceView(client: i.client, alive: i.alive),
      _ => null,
    };

Widget? _advanced(String label, DestinationInputs i) => switch (label) {
      'Receipts' => ReceiptsView(
          client: i.client,
          alive: i.alive,
          focusLeaf:
              i.pendingArgument is String ? i.pendingArgument! as String : null,
        ),
      'Usage' => UsageView(client: i.client, alive: i.alive),
      'Instruments' => InstrumentsView(client: i.client, alive: i.alive),
      'Science' =>
        ScienceView(client: i.client, alive: i.alive, settings: i.settings),
      'World' => WorldView(world: i.world, alive: i.alive, client: i.client),
      'Lanes' => LanesView(
          roster: i.roster,
          alive: i.alive,
          onProbe: i.onProbe,
          onInstall: i.onInstall,
        ),
      'Train' => TrainView(client: i.client, alive: i.alive),
      'Uplift' => UpliftView(client: i.client, alive: i.alive),
      'Family' => FamilyView(client: i.client, alive: i.alive),
      'Plugins' => PluginsView(client: i.client, alive: i.alive),
      _ => null,
    };

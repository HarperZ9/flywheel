import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_roadmap.dart';
import '../client/gateway_swarms.dart';
import '../controllers/journey_controller.dart';
import '../ide/code_buffer_session.dart';
import '../ide/unsaved_work_guard.dart';
import '../models/gateway_models.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
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
import '../views/relay_view.dart';
import '../views/lessons_view.dart';
import '../views/lint_view.dart';
import '../views/memory_view.dart';
import '../views/plan_view.dart';
import '../views/plugins_view.dart';
import '../views/projects_view.dart';
import '../views/receipts_view.dart';
import '../views/roadmap_view.dart';
import '../views/science_view.dart';
import '../views/swarms_view.dart';
import '../views/studio_view.dart';
import '../views/train_view.dart';
import '../views/uplift_view.dart';
import '../views/usage_view.dart';
import '../views/workflows_view.dart';
import '../views/world_view.dart';
import '../widgets/fw.dart';
import '../widgets/side_rail.dart';

/// Rail entries derive from the frozen catalog: one source of truth, so
/// the rail can never drift from the route contract.
final flywheelDestinations = destinationCatalog
    .map((spec) => RailDestination(spec.label,
        abbr: spec.abbr, group: spec.group.name))
    .toList();

DestinationId destinationForLabel(String label) =>
    destinationCatalog
        .firstWhere((spec) => spec.label == label,
            orElse: () => destinationCatalog.first)
        .id;

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

Widget buildDestinationView(DestinationId id, DestinationInputs input) =>
    _work(id, input) ??
    _chat(id, input) ??
    _code(id, input) ??
    _evidence(id, input) ??
    _advanced(id, input) ??
    const FwEmpty('Unknown view');

Widget? _work(DestinationId id, DestinationInputs i) => switch (id) {
      DestinationId.journey => JourneyView(controller: i.journey),
      DestinationId.plan =>
        PlanView(client: i.client, alive: i.alive, settings: i.settings),
      DestinationId.workflows => WorkflowsView(
          client: i.client, alive: i.alive, settings: i.settings),
      DestinationId.projects => ProjectsView(client: i.client, alive: i.alive),
      DestinationId.swarms => SwarmsView(
          api: SwarmsApi(baseUrl: i.client.baseUrl), alive: i.alive),
      DestinationId.roadmap => RoadmapView(
          api: RoadmapApi(baseUrl: i.client.baseUrl), alive: i.alive),
      _ => null,
    };

Widget? _chat(DestinationId id, DestinationInputs i) => switch (id) {
      DestinationId.chat =>
        AgentView(client: i.client, alive: i.alive, settings: i.settings),
      DestinationId.compare =>
        CompareView(client: i.client, alive: i.alive, settings: i.settings),
      DestinationId.models => EndpointsView(client: i.client, alive: i.alive),
      DestinationId.companion => CompanionView(client: i.client, alive: i.alive),
      _ => null,
    };

Widget? _code(DestinationId id, DestinationInputs i) => switch (id) {
      DestinationId.code => CodeView(
          client: i.client,
          alive: i.alive,
          settings: i.settings,
          session: i.code,
          guard: i.codeGuard),
      DestinationId.eval => EvalView(client: i.client, alive: i.alive),
      DestinationId.audit => AuditView(client: i.client, alive: i.alive),
      DestinationId.lint => LintView(client: i.client, alive: i.alive),
      DestinationId.relay => RelayView(client: i.client, alive: i.alive),
      _ => null,
    };

Widget? _evidence(DestinationId id, DestinationInputs i) => switch (id) {
      DestinationId.receipts => ReceiptsView(
          client: i.client,
          alive: i.alive,
          focusLeaf:
              i.pendingArgument is String ? i.pendingArgument! as String : null,
        ),
      DestinationId.science =>
        ScienceView(client: i.client, alive: i.alive, settings: i.settings),
      DestinationId.world =>
        WorldView(world: i.world, alive: i.alive, client: i.client),
      DestinationId.memory => MemoryView(client: i.client, alive: i.alive),
      DestinationId.governance =>
        GovernanceView(client: i.client, alive: i.alive),
      DestinationId.usage => UsageView(client: i.client, alive: i.alive),
      _ => null,
    };

Widget? _advanced(DestinationId id, DestinationInputs i) => switch (id) {
      DestinationId.studio => StudioView(
          world: i.world, roster: i.roster, alive: i.alive, client: i.client),
      DestinationId.graph => GraphView(client: i.client, alive: i.alive),
      DestinationId.feeds => FeedsView(client: i.client, alive: i.alive),
      DestinationId.discourse =>
        DiscourseView(client: i.client, alive: i.alive, settings: i.settings),
      DestinationId.academy => AcademyView(client: i.client, alive: i.alive),
      DestinationId.lessons => LessonsView(client: i.client, alive: i.alive),
      DestinationId.instruments =>
        InstrumentsView(client: i.client, alive: i.alive),
      DestinationId.lanes => LanesView(
          roster: i.roster,
          alive: i.alive,
          onProbe: i.onProbe,
          onInstall: i.onInstall,
        ),
      DestinationId.train => TrainView(client: i.client, alive: i.alive),
      DestinationId.uplift => UpliftView(client: i.client, alive: i.alive),
      DestinationId.family => FamilyView(client: i.client, alive: i.alive),
      DestinationId.plugins => PluginsView(client: i.client, alive: i.alive),
      _ => null,
    };

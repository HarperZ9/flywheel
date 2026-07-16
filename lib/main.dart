// main.dart — Flywheel Desktop: the native surface for the one platform.
//
// A Flutter Desktop client for the Flywheel gateway (`flywheel up`,
// 127.0.0.1:8799). The engine keeps the loop, receipts, lanes, and routing;
// this app renders them. If the gateway is offline the app can start it as
// a child process, so no terminal is ever required.

import 'dart:async';

import 'package:flutter/material.dart';

import 'client/gateway_client.dart';
import 'models/gateway_models.dart';
import 'services/gateway_process.dart';
import 'services/settings.dart';
import 'theme/flywheel_theme.dart';
import 'views/agent_view.dart';
import 'views/academy_view.dart';
import 'views/code_view.dart';
import 'views/compare_view.dart';
import 'views/companion_view.dart';
import 'views/endpoints_view.dart';
import 'views/family_view.dart';
import 'views/feeds_view.dart';
import 'views/graph_view.dart';
import 'views/instruments_view.dart';
import 'views/lanes_view.dart';
import 'views/lint_view.dart';
import 'views/memory_view.dart';
import 'views/plan_view.dart';
import 'views/plugins_view.dart';
import 'views/discourse_view.dart';
import 'views/projects_view.dart';
import 'views/receipts_view.dart';
import 'views/science_view.dart';
import 'views/studio_view.dart';
import 'views/train_view.dart';
import 'views/uplift_view.dart';
import 'views/workflows_view.dart';
import 'views/world_view.dart';
import 'widgets/appearance_panel.dart';
import 'widgets/fw.dart';
import 'widgets/side_rail.dart';
import 'widgets/status_bar.dart';

void main() {
  runApp(FlywheelApp(settings: DesktopSettings.load()));
}

class FlywheelApp extends StatefulWidget {
  final DesktopSettings settings;
  const FlywheelApp({super.key, required this.settings});

  @override
  State<FlywheelApp> createState() => _FlywheelAppState();
}

class _FlywheelAppState extends State<FlywheelApp> {
  late ThemeMode _mode = widget.settings.themeMode;

  void _toggleTheme() {
    setState(() {
      _mode = switch (_mode) {
        ThemeMode.system => ThemeMode.light,
        ThemeMode.light => ThemeMode.dark,
        ThemeMode.dark => ThemeMode.system,
      };
      widget.settings.themeMode = _mode;
      widget.settings.save();
    });
  }

  /// Appearance changes (fonts, scale) mutate settings and land here.
  void _appearanceChanged() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final s = widget.settings;
    return MaterialApp(
      title: 'Flywheel',
      debugShowCheckedModeBanner: false,
      theme: flywheelLightTheme(
          textFamily: s.textFamily,
          monoFamily: s.monoFamily,
          groundPreset: s.groundPreset),
      darkTheme: flywheelDarkTheme(
          textFamily: s.textFamily,
          monoFamily: s.monoFamily,
          groundPreset: s.groundPreset),
      themeMode: _mode,
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
            textScaler: TextScaler.linear(s.uiScale.clamp(0.8, 1.4))),
        child: child!,
      ),
      home: FlywheelShell(
          themeMode: _mode,
          onToggleTheme: _toggleTheme,
          onAppearanceChanged: _appearanceChanged,
          settings: widget.settings),
    );
  }
}

class FlywheelShell extends StatefulWidget {
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;
  final VoidCallback? onAppearanceChanged;
  final DesktopSettings settings;
  const FlywheelShell(
      {super.key,
      required this.themeMode,
      required this.onToggleTheme,
      this.onAppearanceChanged,
      required this.settings});

  @override
  State<FlywheelShell> createState() => _FlywheelShellState();
}

class _FlywheelShellState extends State<FlywheelShell> {
  final _client = GatewayClient();
  final _gateway = GatewayProcess();
  int _selectedIndex = 0;
  bool _gatewayAlive = false;
  String _statusMessage = 'connecting…';
  String? _startError;

  LaneRoster? _roster;
  WorldDoc? _world;
  Timer? _timer;

  late bool _railCollapsed = widget.settings.railCollapsed;

  // Grouped by what the user came to DO, not by how the engine is built. The rail
  // opens on Chat; the accountability surfaces live under Advanced, present for
  // those who want them, out of the newcomer's way. Views are mapped by label
  // (below), so this order can change freely without touching the mapping.
  static const _destinations = [
    RailDestination('Chat', abbr: 'CH', group: 'Start'),
    RailDestination('Compare', abbr: 'CP', group: 'Start'),
    RailDestination('Models', abbr: 'MD', group: 'Start'),
    RailDestination('Code', abbr: 'CO', group: 'Do'),
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
    RailDestination('Receipts', abbr: 'RC', group: 'Advanced'),
    RailDestination('Instruments', abbr: 'IS', group: 'Advanced'),
    RailDestination('Science', abbr: 'SC', group: 'Advanced'),
    RailDestination('World', abbr: 'WD', group: 'Advanced'),
    RailDestination('Lanes', abbr: 'LN', group: 'Advanced'),
    RailDestination('Train', abbr: 'TR', group: 'Advanced'),
    RailDestination('Uplift', abbr: 'UP', group: 'Advanced'),
    RailDestination('Family', abbr: 'FA', group: 'Advanced'),
    RailDestination('Plugins', abbr: 'PL', group: 'Advanced'),
  ];

  @override
  void initState() {
    super.initState();
    _poll();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _client.close();
    _gateway.stopIfOwned();
    super.dispose();
  }

  Future<void> _poll() async {
    final alive = await _client.isAlive();
    if (!alive) {
      if (mounted) {
        setState(() {
          _gatewayAlive = false;
          _statusMessage = 'engine offline';
        });
      }
      return;
    }
    try {
      final roster = await _client.laneRoster();
      final world = await _client.projectedWorld();
      if (mounted) {
        setState(() {
          _gatewayAlive = true;
          _startError = null;
          _roster = roster;
          _world = world;
          final live = roster.byStatus['live'] ?? 0;
          _statusMessage = '$live/${roster.nLanes} lanes live';
        });
      }
    } catch (e) {
      if (mounted) setState(() => _statusMessage = 'error: $e');
    }
  }

  Future<void> _startEngine() async {
    setState(() => _statusMessage = 'starting engine…');
    final err = await _gateway.start();
    if (err != null && mounted) {
      setState(() {
        _startError = err;
        _statusMessage = 'engine offline';
      });
      return;
    }
    // Give the gateway a moment, then resume normal polling.
    await Future.delayed(const Duration(seconds: 2));
    _poll();
  }

  Future<void> _probeLanes() async {
    setState(() => _statusMessage = 'probing lanes…');
    try {
      final roster = await _client.laneRoster(probe: true);
      if (mounted) setState(() => _roster = roster);
    } catch (e) {
      if (mounted) setState(() => _statusMessage = 'probe failed: $e');
    }
    _poll();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Expanded(
            child: Row(
              children: [
                SideRail(
                  destinations: _destinations,
                  selectedIndex: _selectedIndex,
                  onSelect: (i) => setState(() => _selectedIndex = i),
                  themeMode: widget.themeMode,
                  onToggleTheme: widget.onToggleTheme,
                  collapsed: _railCollapsed,
                  onToggleCollapse: () => setState(() {
                    _railCollapsed = !_railCollapsed;
                    widget.settings.railCollapsed = _railCollapsed;
                    widget.settings.save();
                  }),
                  onOpenAppearance: () => showAppearancePanel(
                      context,
                      widget.settings,
                      widget.onAppearanceChanged ?? () {}),
                ),
                Expanded(child: _activeView()),
              ],
            ),
          ),
          StatusBar(
            alive: _gatewayAlive,
            message: _statusMessage,
            startError: _startError,
            world: _world,
            onStartEngine: _startEngine,
          ),
        ],
      ),
    );
  }

  Widget _activeView() {
    switch (_destinations[_selectedIndex].label) {
      case 'Chat':
        return AgentView(
            client: _client, alive: _gatewayAlive, settings: widget.settings);
      case 'Compare':
        return CompareView(
            client: _client, alive: _gatewayAlive, settings: widget.settings);
      case 'Models':
        return EndpointsView(client: _client, alive: _gatewayAlive);
      case 'Code':
        return CodeView(
            client: _client, alive: _gatewayAlive, settings: widget.settings);
      case 'Companion':
        return CompanionView(client: _client, alive: _gatewayAlive);
      case 'Plan':
        return PlanView(client: _client, alive: _gatewayAlive);
      case 'Workflows':
        return WorkflowsView(client: _client, alive: _gatewayAlive);
      case 'Studio':
        return StudioView(
            world: _world, roster: _roster, alive: _gatewayAlive);
      case 'Lint':
        return LintView(client: _client, alive: _gatewayAlive);
      case 'Memory':
        return MemoryView(client: _client, alive: _gatewayAlive);
      case 'Graph':
        return GraphView(client: _client, alive: _gatewayAlive);
      case 'Projects':
        return ProjectsView(client: _client, alive: _gatewayAlive);
      case 'Feeds':
        return FeedsView(client: _client, alive: _gatewayAlive);
      case 'Discourse':
        return DiscourseView(client: _client, alive: _gatewayAlive);
      case 'Academy':
        return AcademyView(client: _client, alive: _gatewayAlive);
      case 'Receipts':
        return ReceiptsView(client: _client, alive: _gatewayAlive);
      case 'Instruments':
        return InstrumentsView(client: _client, alive: _gatewayAlive);
      case 'Science':
        return ScienceView(client: _client, alive: _gatewayAlive);
      case 'World':
        return WorldView(world: _world, alive: _gatewayAlive);
      case 'Lanes':
        return LanesView(
            roster: _roster, alive: _gatewayAlive, onProbe: _probeLanes);
      case 'Train':
        return TrainView(client: _client, alive: _gatewayAlive);
      case 'Uplift':
        return UpliftView(client: _client, alive: _gatewayAlive);
      case 'Family':
        return FamilyView(client: _client, alive: _gatewayAlive);
      case 'Plugins':
        return PluginsView(client: _client, alive: _gatewayAlive);
      default:
        return const FwEmpty('Unknown view');
    }
  }

}

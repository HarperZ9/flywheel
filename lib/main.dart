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
import 'views/code_view.dart';
import 'views/companion_view.dart';
import 'views/endpoints_view.dart';
import 'views/graph_view.dart';
import 'views/lanes_view.dart';
import 'views/memory_view.dart';
import 'views/plugins_view.dart';
import 'views/projects_view.dart';
import 'views/receipts_view.dart';
import 'views/studio_view.dart';
import 'views/train_view.dart';
import 'views/workflows_view.dart';
import 'views/world_view.dart';
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

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flywheel',
      debugShowCheckedModeBanner: false,
      theme: flywheelLightTheme(),
      darkTheme: flywheelDarkTheme(),
      themeMode: _mode,
      home: FlywheelShell(
          themeMode: _mode,
          onToggleTheme: _toggleTheme,
          settings: widget.settings),
    );
  }
}

class FlywheelShell extends StatefulWidget {
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;
  final DesktopSettings settings;
  const FlywheelShell(
      {super.key,
      required this.themeMode,
      required this.onToggleTheme,
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

  static const _destinations = [
    RailDestination('Projects', abbr: 'PR'),
    RailDestination('Lanes', abbr: 'LN'),
    RailDestination('Code', abbr: 'CO'),
    RailDestination('World', abbr: 'WD'),
    RailDestination('Graph', abbr: 'GR'),
    RailDestination('Receipts', abbr: 'RC'),
    RailDestination('Companion', abbr: 'CM'),
    RailDestination('Agent', abbr: 'AG'),
    RailDestination('Workflows', abbr: 'WF'),
    RailDestination('Studio', abbr: 'ST'),
    RailDestination('Train', abbr: 'TR'),
    RailDestination('Memory', abbr: 'ME'),
    RailDestination('Plugins', abbr: 'PL'),
    RailDestination('Endpoints', abbr: 'EP'),
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
    switch (_selectedIndex) {
      case 0:
        return ProjectsView(client: _client, alive: _gatewayAlive);
      case 1:
        return LanesView(
            roster: _roster, alive: _gatewayAlive, onProbe: _probeLanes);
      case 2:
        return CodeView(
            client: _client, alive: _gatewayAlive, settings: widget.settings);
      case 3:
        return WorldView(world: _world, alive: _gatewayAlive);
      case 4:
        return GraphView(world: _world, roster: _roster, alive: _gatewayAlive);
      case 5:
        return ReceiptsView(client: _client, alive: _gatewayAlive);
      case 6:
        return CompanionView(client: _client, alive: _gatewayAlive);
      case 7:
        return AgentView(client: _client, alive: _gatewayAlive);
      case 8:
        return WorkflowsView(client: _client, alive: _gatewayAlive);
      case 9:
        return StudioView(
            world: _world, roster: _roster, alive: _gatewayAlive);
      case 10:
        return TrainView(client: _client, alive: _gatewayAlive);
      case 11:
        return MemoryView(client: _client, alive: _gatewayAlive);
      case 12:
        return PluginsView(client: _client, alive: _gatewayAlive);
      case 13:
        return EndpointsView(client: _client, alive: _gatewayAlive);
      default:
        return const FwEmpty('Unknown view');
    }
  }

}

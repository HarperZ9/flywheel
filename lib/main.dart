// main.dart — Flywheel Desktop: the native surface.
//
// A Flutter Desktop app that is a native client for the Flywheel Python
// gateway. The gateway (started by `flywheel up`) runs on 127.0.0.1:8799; this
// app polls /api/lanes and /api/world every 5s for live state and renders them
// in a native window with a navigation rail, menus, and the verdict-color
// token system.
//
// Architecture: Flutter = native UI. Python gateway = backend (loop, receipts,
// lanes). This app does not reimplement the loop; it displays it.

import 'dart:async';
import 'package:flutter/material.dart';

import 'client/gateway_client.dart';
import 'models/gateway_models.dart';
import 'theme/flywheel_theme.dart';
import 'views/lanes_view.dart';
import 'views/world_view.dart';

void main() {
  runApp(const FlywheelApp());
}

class FlywheelApp extends StatelessWidget {
  const FlywheelApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flywheel',
      debugShowCheckedModeBanner: false,
      theme: flywheelLightTheme(),
      darkTheme: flywheelDarkTheme(),
      themeMode: ThemeMode.system,
      home: const FlywheelShell(),
    );
  }
}

class FlywheelShell extends StatefulWidget {
  const FlywheelShell({super.key});

  @override
  State<FlywheelShell> createState() => _FlywheelShellState();
}

class _FlywheelShellState extends State<FlywheelShell> {
  final _client = GatewayClient();
  int _selectedIndex = 0;
  bool _gatewayAlive = false;
  String _statusMessage = 'connecting…';

  // Live data
  LaneRoster? _roster;
  WorldDoc? _world;
  Timer? _timer;

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
    super.dispose();
  }

  Future<void> _poll() async {
    final alive = await _client.isAlive();
    if (!alive) {
      if (mounted) {
        setState(() {
          _gatewayAlive = false;
          _statusMessage = 'gateway offline — run `flywheel up`';
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
          _roster = roster;
          _world = world;
          final live = roster.byStatus['live'] ?? 0;
          _statusMessage =
              '$live/${roster.nLanes} lanes live · ${world.rootHash.substring(0, 16)}…';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusMessage = 'error: $e';
        });
      }
    }
  }

  Future<void> _probeLanes() async {
    setState(() => _statusMessage = 'probing lanes…');
    try {
      final roster = await _client.laneRoster(probe: true);
      if (mounted) setState(() => _roster = roster);
    } catch (_) {}
    _poll();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          // Navigation rail (the sidebar / menu)
          NavigationRail(
            selectedIndex: _selectedIndex,
            onDestinationSelected: (i) => setState(() => _selectedIndex = i),
            labelType: NavigationRailLabelType.all,
            leading: const Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: Column(
                children: [
                  Icon(Icons.all_inclusive, size: 28),
                  SizedBox(height: 4),
                  Text('Flywheel',
                      style: TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w700)),
                ],
              ),
            ),
            destinations: const [
              NavigationRailDestination(
                  icon: Icon(Icons.dns_outlined),
                  selectedIcon: Icon(Icons.dns),
                  label: Text('Lanes')),
              NavigationRailDestination(
                  icon: Icon(Icons.public_outlined),
                  selectedIcon: Icon(Icons.public),
                  label: Text('World')),
              NavigationRailDestination(
                  icon: Icon(Icons.receipt_outlined),
                  selectedIcon: Icon(Icons.receipt),
                  label: Text('Receipts')),
              NavigationRailDestination(
                  icon: Icon(Icons.chat_outlined),
                  selectedIcon: Icon(Icons.chat),
                  label: Text('Companion')),
              NavigationRailDestination(
                  icon: Icon(Icons.hub_outlined),
                  selectedIcon: Icon(Icons.hub),
                  label: Text('Endpoints')),
            ],
          ),
          const VerticalDivider(width: 1),
          // Main content area
          Expanded(
            child: Column(
              children: [
                // Status bar
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surface,
                    border: Border(
                        bottom: BorderSide(
                            color: Theme.of(context).dividerColor, width: 1)),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        _gatewayAlive
                            ? Icons.check_circle
                            : Icons.error_outline,
                        size: 14,
                        color: _gatewayAlive
                            ? FlywheelColors.match
                            : FlywheelColors.missing,
                      ),
                      const SizedBox(width: 6),
                      Text(_statusMessage,
                          style: TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 12,
                              color: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.color)),
                      const Spacer(),
                      Text('127.0.0.1:8799',
                          style: TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 11,
                              color: Theme.of(context).hintColor)),
                    ],
                  ),
                ),
                // The active view
                Expanded(child: _activeView()),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _activeView() {
    switch (_selectedIndex) {
      case 0:
        return LanesView(roster: _roster, onProbe: _probeLanes);
      case 1:
        return WorldView(world: _world);
      case 2:
        return _placeholder(
            'Receipts', 'The verified-envelope ledger lands here (Phase 2c).');
      case 3:
        return _placeholder(
            'Companion', 'The chat surface with verdict chips lands here (Phase 2d).');
      case 4:
        return _placeholder(
            'Endpoints', 'The universal router roster lands here (Phase 2e).');
      default:
        return const Center(child: Text('Unknown view'));
    }
  }

  Widget _placeholder(String title, String message) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.construction,
              size: 48, color: FlywheelColors.unverifiable),
          const SizedBox(height: 12),
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Text(message,
              style: Theme.of(context).textTheme.bodySmall,
              textAlign: TextAlign.center),
        ],
      ),
    );
  }
}

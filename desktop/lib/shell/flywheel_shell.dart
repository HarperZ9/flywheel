import 'dart:async';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../client/journey_api.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../models/connection_state.dart';
import '../models/gateway_models.dart';
import '../services/gateway_process.dart';
import '../services/gateway_status.dart';
import '../services/code_draft_store.dart';
import '../services/journey_draft_store.dart';
import '../services/journey_session_store.dart';
import '../services/settings.dart';
import '../ide/code_buffer_session.dart';
import '../ide/unsaved_work_guard.dart';
import '../widgets/appearance_panel.dart';
import '../widgets/flywheel_nav.dart';
import '../widgets/operation_grant_sheet.dart';
import '../widgets/side_rail.dart';
import '../widgets/status_bar.dart';
import 'view_factory.dart';

final class FlywheelDependencies {
  const FlywheelDependencies({
    required this.client,
    required this.gateway,
    required this.journey,
    required this.code,
    this.closePrompt,
    this.status,
  });

  factory FlywheelDependencies.production() {
    final client = GatewayClient();
    return FlywheelDependencies(
      client: client,
      gateway: GatewayProcess(),
      code: CodeBufferSession(draftStore: CodeDraftStore()),
      journey: JourneyController(
        api: GatewayJourneyApi(client),
        draftStore: JourneyDraftStore(),
        sessionStore: JourneySessionStore(),
      ),
      status: GatewayStatusService.production(
        baseUrl: client.baseUrl,
        fallbackAlive: () => client.isAlive(),
      ),
    );
  }

  final GatewayClient client;
  final GatewayProcess gateway;
  final JourneyController journey;
  final CodeBufferSession code;
  final CloseChoicePrompt? closePrompt;

  /// The typed connection probe. Null in hand-built test dependencies,
  /// where the shell falls back to the client's own liveness check; the
  /// typed route is covered by connection_state_test and the engine's
  /// desktop-status route tests.
  final GatewayStatusService? status;

  void dispose() {
    journey.dispose();
    code.dispose();
    client.close();
    gateway.stopIfOwned();
  }
}

class FlywheelShell extends StatefulWidget {
  const FlywheelShell({
    super.key,
    required this.themeMode,
    required this.onToggleTheme,
    required this.settings,
    this.onAppearanceChanged,
    this.dependencies,
  });

  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;
  final VoidCallback? onAppearanceChanged;
  final DesktopSettings settings;
  final FlywheelDependencies? dependencies;

  @override
  State<FlywheelShell> createState() => _FlywheelShellState();
}

class _FlywheelShellState extends State<FlywheelShell> {
  late final FlywheelDependencies _dependencies;
  late bool _railCollapsed = widget.settings.railCollapsed;
  late double _railWidth = widget.settings.railWidth;
  int _selectedIndex = 0;
  bool _gatewayAlive = false;
  ConnectionStatus _connection = ConnectionStatus.starting;
  String _statusMessage = 'connecting…';
  String? _startError;
  LaneRoster? _roster;
  WorldDoc? _world;
  Timer? _timer;
  Object? _pendingArgument;
  late final UnsavedWorkGuard _guard;
  late final GatewayOperationController _operations;
  GatewayStatusService? get _status => widget.dependencies?.status;
  late final AppLifecycleListener _lifecycle;
  int _navigationGeneration = 0;

  @override
  void initState() {
    super.initState();
    _dependencies = widget.dependencies ?? FlywheelDependencies.production();
    _operations =
        GatewayOperationController(GatewayGrantClient(_dependencies.client));
    _guard = UnsavedWorkGuard(
        session: _dependencies.code,
        prompt: _dependencies.closePrompt ??
            (request) => showUnsavedWorkPrompt(context, request));
    _lifecycle = AppLifecycleListener(onExitRequested: _requestExit);
    unawaited(_dependencies.journey.initialize());
    unawaited(_poll());
    _timer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => unawaited(_poll()),
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    _lifecycle.dispose();
    _operations.dispose();
    _dependencies.dispose();
    super.dispose();
  }

  void _goTo(String label, {Object? arg}) {
    final index =
        flywheelDestinations.indexWhere((item) => item.label == label);
    if (index >= 0) unawaited(_requestSelection(index, arg: arg));
  }

  Future<void> _requestSelection(int index, {Object? arg}) async {
    if (index == _selectedIndex) {
      if (arg != null) setState(() => _pendingArgument = arg);
      return;
    }
    final generation = ++_navigationGeneration;
    final allowed =
        await _guard.requestNavigation(flywheelDestinations[index].label);
    if (!allowed || !mounted || generation != _navigationGeneration) return;
    setState(() {
      _selectedIndex = index;
      _pendingArgument = arg;
    });
  }

  Future<AppExitResponse> _requestExit() async =>
      await _guard.requestApplicationExit()
          ? AppExitResponse.exit
          : AppExitResponse.cancel;

  Future<void> _poll() async {
    final service = _status;
    if (service == null) {
      // Hand-built dependencies (tests): the legacy liveness check.
      final alive = await _dependencies.client.isAlive();
      if (!mounted) return;
      setState(() {
        _gatewayAlive = alive;
        _connection =
            alive ? _connection : ConnectionStatus.offline;
        _statusMessage =
            alive ? _statusMessage : ConnectionStatus.offline.detail;
      });
      if (alive) await _loadGatewayStatus();
      return;
    }
    final status = await service.probe();
    if (!mounted) return;
    setState(() {
      _connection = status;
      _gatewayAlive = status.alive;
      _statusMessage = status.detail;
    });
    if (!status.alive) return;
    await _loadGatewayStatus();
  }

  Future<void> _loadGatewayStatus() async {
    try {
      final roster = await _dependencies.client.laneRoster();
      final world = await _dependencies.client.projectedWorld();
      if (!mounted) return;
      setState(() {
        _gatewayAlive = true;
        _startError = null;
        _roster = roster;
        _world = world;
        _statusMessage =
            '${roster.byStatus['live'] ?? 0}/${roster.nLanes} lanes live';
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _connection = ConnectionStatus.typed(ConnectionPhase.degraded,
              lanesLive: _connection.lanesLive,
              lanesTotal: _connection.lanesTotal,
              detail: 'lanes unreadable · degraded');
          _statusMessage = 'error: $error';
        });
      }
    }
  }

  Future<void> _startEngine() async {
    setState(() {
      _connection = ConnectionStatus.starting;
      _statusMessage = 'starting engine…';
    });
    final error = await _dependencies.gateway.start();
    if (!mounted) {
      if (error == null) _dependencies.gateway.stopIfOwned();
      return;
    }
    if (error != null) {
      setState(() {
        _startError = error;
        _statusMessage = 'engine offline';
      });
      return;
    }
    await Future<void>.delayed(const Duration(seconds: 2));
    unawaited(_poll());
  }

  Future<void> _probeLanes() async {
    if (!mounted) return;
    setState(() => _statusMessage = 'probing lanes…');
    try {
      final roster = await _dependencies.client.laneRoster(probe: true);
      if (mounted) setState(() => _roster = roster);
    } catch (error) {
      if (mounted) setState(() => _statusMessage = 'probe failed: $error');
    }
    if (mounted) unawaited(_poll());
  }

  Future<Map<String, dynamic>> _installLane(String name) async {
    final result = await _dependencies.client.installLane(name);
    if (mounted) unawaited(_probeLanes());
    return result;
  }

  Widget _activeView() {
    final label = flywheelDestinations[_selectedIndex].label;
    final argument = label == 'Receipts' ? _pendingArgument : null;
    if (label == 'Receipts') _pendingArgument = null;
    return buildDestinationView(
      label,
      DestinationInputs(
        client: _dependencies.client,
        journey: _dependencies.journey,
        code: _dependencies.code,
        codeGuard: _guard,
        alive: _gatewayAlive,
        settings: widget.settings,
        pendingArgument: argument,
        roster: _roster,
        world: _world,
        onProbe: _probeLanes,
        onInstall: _installLane,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return GatewayOperationScope(
      authorize: journeyGatewayAuthorizer(_operations, _dependencies.journey),
      child: Scaffold(
        body: FlywheelNav(
          goTo: _goTo,
          child: Column(
            children: [
              Expanded(
                child: Row(children: [_rail(), Expanded(child: _activeView())]),
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
        ),
      ),
    );
  }

  Widget _rail() => SideRail(
        destinations: flywheelDestinations,
        selectedIndex: _selectedIndex,
        onSelect: (index) => unawaited(_requestSelection(index)),
        themeMode: widget.themeMode,
        onToggleTheme: widget.onToggleTheme,
        collapsed: _railCollapsed,
        width: _railWidth,
        onResize: _resizeRail,
        onToggleCollapse: _toggleRail,
        onOpenAppearance: () => showAppearancePanel(
          context,
          widget.settings,
          widget.onAppearanceChanged ?? () {},
        ),
      );

  void _resizeRail(double width) {
    setState(() => _railWidth = width);
    widget.settings.railWidth = width;
    widget.settings.save();
  }

  void _toggleRail() {
    setState(() => _railCollapsed = !_railCollapsed);
    widget.settings.railCollapsed = _railCollapsed;
    widget.settings.save();
  }
}

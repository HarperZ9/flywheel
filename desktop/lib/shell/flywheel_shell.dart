// flywheel_shell.dart -- the desktop shell: one dependency graph, typed
// navigation over the frozen 30-destination catalog, the command palette,
// and the status coordinator. Views render; this composes and routes.
import 'dart:async';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../client/journey_api.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../navigation/app_route.dart';
import '../navigation/navigation_controller.dart';
import '../navigation/view_cache.dart';
import '../services/code_draft_store.dart';
import '../services/gateway_process.dart';
import '../services/gateway_status.dart';
import '../services/journey_draft_store.dart';
import '../services/journey_session_store.dart';
import '../services/settings.dart';
import '../ide/code_buffer_session.dart';
import '../ide/unsaved_work_guard.dart';
import '../widgets/appearance_panel.dart';
import '../widgets/command_palette.dart';
import '../widgets/flywheel_nav.dart';
import '../widgets/operation_grant_sheet.dart';
import '../widgets/shell_rail.dart';
import '../widgets/status_bar.dart';
import 'gateway_status_coordinator.dart';
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
  late final NavigationController _navigation;
  late final GatewayStatusCoordinator _coordinator;
  late final UnsavedWorkGuard _guard;
  late final GatewayOperationController _operations;
  late final AppLifecycleListener _lifecycle;
  final ViewCache _views = ViewCache();
  final TextEditingController _search = TextEditingController();
  Object? _pendingArgument;

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
    _navigation = NavigationController(guard: _guard.requestNavigation);
    _coordinator = GatewayStatusCoordinator(
      client: _dependencies.client,
      status: _dependencies.status,
      startEngine: () => _dependencies.gateway.start(),
      onOrphanStart: _dependencies.gateway.stopIfOwned,
    );    _lifecycle = AppLifecycleListener(onExitRequested: _requestExit);
    unawaited(_dependencies.journey.initialize());
    _coordinator.beginPolling();
  }

  @override
  void dispose() {
    _coordinator.disposePolling();
    _coordinator.dispose();
    _navigation.dispose();
    _search.dispose();
    _lifecycle.dispose();
    _operations.dispose();
    _dependencies.dispose();
    super.dispose();
  }

  void _goTo(DestinationId routeId, {Object? arg}) {
    if (arg != null) setState(() => _pendingArgument = arg);
    unawaited(_navigation
        .go(AppLocation(routeId: routeId))
        .then((ok) => mounted ? setState(() {}) : null));
  }

  Future<AppExitResponse> _requestExit() async =>
      await _guard.requestApplicationExit()
          ? AppExitResponse.exit
          : AppExitResponse.cancel;

  Widget _activeView() {
    final location = _navigation.current;
    final argument =
        location.routeId == DestinationId.receipts ? _pendingArgument : null;
    if (location.routeId == DestinationId.receipts) _pendingArgument = null;
    return AnimatedBuilder(
        animation: Listenable.merge([_coordinator, _navigation]),
        builder: (context, _) => _views.viewFor(location, (_) {
              return buildDestinationView(
                location.routeId,
                DestinationInputs(
                  client: _dependencies.client,
                  journey: _dependencies.journey,
                  code: _dependencies.code,
                  codeGuard: _guard,
                  alive: _coordinator.alive,
                  settings: widget.settings,
                  pendingArgument: argument,
                  roster: _coordinator.roster,
                  world: _coordinator.world,
                  onProbe: () => unawaited(_coordinator.probeLanes()),
                  onInstall: (name) async =>
                      await _coordinator.installLane(name),
                ),
              );
            }));
  }

  @override
  Widget build(BuildContext context) {
    return PaletteShortcuts(
      onGo: _goTo,
      child: GatewayOperationScope(
        authorize:
            journeyGatewayAuthorizer(_operations, _dependencies.journey),
        child: Scaffold(
          body: FlywheelNav(
            goTo: _goTo,
            child: Column(
              children: [
                Expanded(
                  child: Row(children: [
                    _rail(),
                    Expanded(child: _activeView()),
                  ]),
                ),
                AnimatedBuilder(
                    animation: _coordinator,
                    builder: (context, _) => StatusBar(
                          alive: _coordinator.alive,
                          message: _coordinator.message,
                          startError: _coordinator.startError,
                          world: _coordinator.world,
                          onStartEngine: () =>
                              unawaited(_coordinator.start()),
                        )),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _rail() {
    return AnimatedBuilder(
        animation: Listenable.merge([_navigation, _coordinator]),
        builder: (context, _) => ShellRail(
              collapsed: _railCollapsed,
              width: _railWidth,
              selected: _navigation.current.routeId,
              search: _search,
              onGo: _goTo,
              onResize: _resizeRail,
              onToggleCollapse: _toggleRail,
              onToggleTheme: widget.onToggleTheme,
              onOpenAppearance: () => showAppearancePanel(
                context,
                widget.settings,
                widget.onAppearanceChanged ?? () {},
              ),
            ));
  }

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

// keyboard shortcut support lives with the palette.

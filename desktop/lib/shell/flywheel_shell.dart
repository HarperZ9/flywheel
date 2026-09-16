import 'dart:async';
import 'dart:io' show Platform;
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';

import '../client/gateway_grants.dart';
import '../client/journey_api.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../controllers/live_screen_sharing.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../navigation/navigation_controller.dart';
import '../navigation/view_cache.dart';
import '../services/settings.dart';
import '../ide/unsaved_work_guard.dart';
import '../assistant/speech_voice.dart';
import '../assistant/voice.dart';
import '../assistant/rowan_action_cue_widget.dart';
import '../assistant/rowan_action_cue_strip.dart';
import '../widgets/appearance_panel.dart';
import '../widgets/command_palette.dart';
import '../widgets/connection_panel.dart';
import '../widgets/flywheel_nav.dart';
import '../widgets/mobile_nav_bar.dart';
import '../widgets/sessions_panel.dart';
import '../widgets/operation_grant_sheet.dart';
import '../widgets/rowan_launch_tour.dart';
import '../widgets/shell_rail.dart';
import '../widgets/status_bar.dart';
import '../widgets/screen_sharing_surface.dart';
import 'flywheel_dependencies.dart';
import 'gateway_status_coordinator.dart';
import 'shell_chrome.dart';
import 'shell_rowan_cues.dart';
import 'view_factory.dart';

export 'flywheel_dependencies.dart';
part 'flywheel_shell_active_view.dart';
part 'flywheel_shell_status.dart';

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
  late final LiveScreenSharing _screenSharing;
  late final ShellRowanCues _rowanCues;
  late final AppLifecycleListener _lifecycle;
  final ViewCache _views = ViewCache();
  Object? _pendingArgument;

  final bool _mobile = Platform.isAndroid || Platform.isIOS;
  late final VoiceInput _voiceInput =
      _mobile ? SpeechVoiceInput() : const SilentVoice();
  late final VoiceOutput _voiceOutput =
      _mobile ? FlutterTtsVoiceOutput() : const SilentVoice();

  @override
  void initState() {
    super.initState();
    _dependencies = widget.dependencies ?? FlywheelDependencies.production();
    _screenSharing = LiveScreenSharing(_dependencies.client);
    _rowanCues = ShellRowanCues(
      operationHost: _dependencies.rowanOperationHost,
      screenSharing: _screenSharing,
    );
    _operations = GatewayOperationController(
      GatewayGrantClient(_dependencies.client),
    );
    _guard = UnsavedWorkGuard(
      session: _dependencies.code,
      prompt: _dependencies.closePrompt ??
          (request) => showUnsavedWorkPrompt(context, request),
    );
    _navigation = NavigationController(
      guard: _guard.requestNavigation,
      initial: _mobile ? const AppLocation(routeId: DestinationId.chat) : null,
    );
    _coordinator = GatewayStatusCoordinator(
      client: _dependencies.client,
      status: _dependencies.status,
      startEngine: () => _dependencies.gateway.start(),
      autoStartEngine: _dependencies.autoStartBundledEngine
          ? () => _dependencies.gateway.startBundled()
          : null,
      onOrphanStart: _dependencies.gateway.stopIfOwned,
      onReady: _dependencies.journey.retryRead,
    );
    _lifecycle = AppLifecycleListener(onExitRequested: _requestExit);
    _coordinator.beginPolling();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || widget.settings.firstRunSeen) return;
      // Set the flag the moment the tour is shown, not on completion, so a
      // force-quit mid-tour does not make it reappear every launch. Replay
      // stays available from the rail.
      widget.settings.firstRunSeen = true;
      widget.settings.save();
      _presentWalkthrough();
    });
  }

  void _presentWalkthrough() {
    if (!mounted) return;
    unawaited(showRowanWalkthrough(
      context,
      onOpenStudio: () => _goTo(DestinationId.studio),
    ));
  }

  @override
  void dispose() {
    unawaited(_rowanCues.dispose());
    _coordinator.disposePolling();
    _coordinator.dispose();
    _navigation.dispose();
    _lifecycle.dispose();
    _operations.dispose();
    _screenSharing.dispose();
    _dependencies.dispose();
    super.dispose();
  }

  void _goTo(DestinationId routeId, {Object? arg}) {
    final from = _navigation.current.routeId;
    unawaited(_navigation.go(AppLocation(routeId: routeId)).then((ok) {
      if (!mounted) return;
      if (ok && from != routeId && routeId == DestinationId.studio) {
        unawaited(_rowanCues.studioOpened());
      }
      setState(() {
        _pendingArgument = ok && _acceptsArgument(routeId) ? arg : null;
      });
    }));
  }

  bool _acceptsArgument(DestinationId routeId) =>
      routeId == DestinationId.receipts || routeId == DestinationId.chat;

  Future<AppExitResponse> _requestExit() async {
    final exit = await _guard.requestApplicationExit();
    if (exit) _dependencies.gateway.stopIfOwned();
    return exit ? AppExitResponse.exit : AppExitResponse.cancel;
  }

  static const double narrowBreakpoint = 640;

  @override
  Widget build(BuildContext context) {
    return ShellRowanCueScope(
        cues: _rowanCues,
        child: PaletteShortcuts(
          onGo: _goTo,
          child: GatewayOperationScope(
            authorize:
                journeyGatewayAuthorizer(_operations, _dependencies.journey),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final narrow = constraints.maxWidth < narrowBreakpoint;
                return Scaffold(
                  drawer: narrow
                      ? Drawer(child: SafeArea(child: _rail(inDrawer: true)))
                      : null,
                  body: FlywheelNav(
                    goTo: _goTo,
                    child: narrow ? _narrowBody(context) : _wideBody(),
                  ),
                );
              },
            ),
          ),
        ));
  }

  Widget _wideBody() => Column(
        children: [
          Expanded(
            child: Row(
              children: [
                _rail(),
                Expanded(child: _activeView()),
              ],
            ),
          ),
          _sharingBar(),
          _statusBar(),
        ],
      );

  Widget _narrowBody(BuildContext context) => SafeArea(
        bottom: false,
        child: Column(
          children: [
            ShellMobileTopBar(
              navigation: _navigation,
              coordinator: _coordinator,
              onToggleTheme: widget.onToggleTheme,
              onAssistant: () => openAssistant(
                  context, _dependencies, _voiceInput, _voiceOutput),
            ),
            Expanded(child: _activeView()),
            _sharingBar(),
            _statusBar(),
            Builder(
              builder: (ctx) => AnimatedBuilder(
                animation: _navigation,
                builder: (_, __) => MobileNavBar(
                  primaries: mobilePrimaryDestinations,
                  selected: _navigation.current.routeId,
                  onGo: _goTo,
                  onMore: () => Scaffold.of(ctx).openDrawer(),
                ),
              ),
            ),
          ],
        ),
      );

  Widget _sharingBar() => ScreenSharingSurface(
      sharing: _screenSharing,
      compact: true,
      onOpenStudio: () => _goTo(DestinationId.studio));

  Widget _rail({bool inDrawer = false}) {
    return AnimatedBuilder(
      animation: Listenable.merge([_navigation, _coordinator]),
      builder: (context, _) => ShellRail(
        collapsed: inDrawer ? false : _railCollapsed,
        width: inDrawer ? 264 : _railWidth,
        selected: _navigation.current.routeId,
        onGo: inDrawer
            ? (routeId) {
                _goTo(routeId);
                Navigator.of(context).maybePop();
              }
            : _goTo,
        onResize: _resizeRail,
        onToggleCollapse: _toggleRail,
        onToggleTheme: widget.onToggleTheme,
        onOpenAppearance: () => showAppearancePanel(
          context,
          widget.settings,
          widget.onAppearanceChanged ?? () {},
        ),
        onOpenConnection: () => showConnectionPanel(context),
        onOpenSessions: () => showSessionsPanel(
          context,
          api: GatewayJourneyApi(_dependencies.client),
          onOpen: (ref, lens) => _dependencies.journey.openSession(ref, lens),
        ),
        inDrawer: inDrawer,
        onOpenAssistant: () =>
            openAssistant(context, _dependencies, _voiceInput, _voiceOutput),
        onOpenRecovery: () => openRecoveryCenter(context, _dependencies),
        onOpenWalkthrough: inDrawer
            ? () {
                Navigator.of(context).maybePop();
                _presentWalkthrough();
              }
            : _presentWalkthrough,
      ),
    );
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

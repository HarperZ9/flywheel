// flywheel_shell.dart -- the desktop shell: one dependency graph, typed
// navigation over the frozen 30-destination catalog, the command palette,
// and the status coordinator. Views render; this composes and routes.
import 'dart:async';
import 'dart:io' show Platform;
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../client/gateway_auth.dart';
import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../client/journey_api.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../navigation/navigation_controller.dart';
import '../navigation/view_cache.dart';
import '../services/code_draft_store.dart';
import '../services/chat_draft_store.dart';
import '../services/gateway_process.dart';
import '../services/gateway_status.dart';
import '../services/connection_config.dart';
import '../services/journey_draft_store.dart';
import '../services/journey_session_store.dart';
import '../services/settings.dart';
import '../ide/code_buffer_session.dart';
import '../ide/unsaved_work_guard.dart';
import '../widgets/appearance_panel.dart';
import '../assistant/assistant_executor.dart';
import '../assistant/speech_voice.dart';
import '../assistant/url_device_sink.dart';
import '../assistant/voice.dart';
import '../widgets/assistant_panel.dart';
import '../widgets/command_palette.dart';
import '../widgets/connection_panel.dart';
import '../widgets/flywheel_nav.dart';
import '../widgets/mobile_nav_bar.dart';
import '../widgets/sessions_panel.dart';
import '../widgets/operation_grant_sheet.dart';
import '../widgets/shell_rail.dart';
import '../models/recovery_item.dart';
import '../services/recovery_catalog.dart';
import '../services/recovery_sources.dart';
import '../views/recovery_center.dart';
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
    // The paired connection decides where the one app talks: loopback + the local
    // gateway.token by default (desktop unchanged), or a remote gateway URL + a
    // paired token when this device reaches another machine's engine.
    final conn = ConnectionStore().load();
    final client = GatewayClient(
      baseUrl: conn.effectiveBaseUrl,
      httpClient: AuthedClient(http.Client(), readToken: conn.tokenSource),
    );
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
        readToken: conn.tokenSource,
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
  Object? _pendingArgument;

  // Voice is a phone capability: a real speech engine on android and ios, a silent
  // stub on desktop so the assistant stays typed-only there. The panel shows a
  // microphone only where a real engine is present.
  final bool _mobile = Platform.isAndroid || Platform.isIOS;
  late final VoiceInput _voiceInput =
      _mobile ? SpeechVoiceInput() : const SilentVoice();
  late final VoiceOutput _voiceOutput =
      _mobile ? FlutterTtsVoiceOutput() : const SilentVoice();

  /// The recovery center opens as an overlay from the shell footer; it is
  /// deliberately not a thirty-first destination.
  void _openRecoveryCenter() {
    final code = _dependencies.code;
    showDialog<void>(
      context: context,
      builder: (dialogContext) => Dialog(
        insetPadding: const EdgeInsets.all(32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Scaffold(
            body: RecoveryCenter(
              catalog: RecoveryCatalog([
                ChatRecoverySource(ChatDraftStore()),
                CodeRecoverySource(code),
                JourneyRecoverySource(JourneyDraftStore(),
                    acknowledgement: JourneyDraftAcknowledgement(
                        'recovery-center-${DateTime.now().microsecondsSinceEpoch}',
                        'a' * 64)),
                InterruptedOperationRecoverySource(() => const []),
                IncompleteMigrationRecoverySource(),
                FailedUpdateRecoverySource(),
              ]),
            ),
          ),
        ),
      ),
    );
  }

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
    _navigation = NavigationController(
      guard: _guard.requestNavigation,
      // A phone opens on Chat, the surface a personal agent answers from;
      // desktop keeps Journey.
      initial: _mobile
          ? const AppLocation(routeId: DestinationId.chat)
          : null,
    );
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

  /// Below this width the app is one pane and the rail moves into a drawer, so
  /// the same shell fits a phone.
  static const double narrowBreakpoint = 640;

  @override
  Widget build(BuildContext context) {
    return PaletteShortcuts(
      onGo: _goTo,
      child: GatewayOperationScope(
        authorize:
            journeyGatewayAuthorizer(_operations, _dependencies.journey),
        child: LayoutBuilder(builder: (context, constraints) {
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
        }),
      ),
    );
  }

  // Desktop: the side rail beside the active view. Byte-identical to before.
  Widget _wideBody() => Column(
        children: [
          Expanded(
            child: Row(children: [
              _rail(),
              Expanded(child: _activeView()),
            ]),
          ),
          _statusBar(),
        ],
      );

  // Phone: one pane under a slim brand strip, a bottom bar of the first-run
  // destinations, and More for the full catalog. The bottom bar's own SafeArea
  // owns the bottom inset, so the outer one does not double-pad it.
  Widget _narrowBody(BuildContext context) => SafeArea(
        bottom: false,
        child: Column(
          children: [
            _mobileTopBar(),
            Expanded(child: _activeView()),
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

  Widget _statusBar() => AnimatedBuilder(
        animation: _coordinator,
        builder: (context, _) => StatusBar(
              alive: _coordinator.alive,
              message: _coordinator.message,
              startError: _coordinator.startError,
              world: _coordinator.world,
              onStartEngine: () => unawaited(_coordinator.start()),
              // A phone reaches a paired engine; it cannot start one locally.
              local: !_mobile,
            ),
      );

  // A slim brand strip. Navigation lives in the bottom bar, so there is no
  // top-bar hamburger: one entry to the full catalog (More), not two.
  Widget _mobileTopBar() => const Material(
        color: Colors.transparent,
        child: Padding(
          padding: EdgeInsets.fromLTRB(12, 8, 12, 4),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text('Flywheel',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          ),
        ),
      );

  Widget _rail({bool inDrawer = false}) {
    return AnimatedBuilder(
        animation: Listenable.merge([_navigation, _coordinator]),
        builder: (context, _) => ShellRail(
              // In the drawer the rail is always expanded at a drawer width, and a
              // tap navigates then closes the drawer.
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
              onOpenAssistant: () => showAssistantPanel(
                context,
                executor: AssistantExecutor(
                  agent: GatewayAgentSink(_dependencies.client),
                  device: UrlLauncherDeviceSink(),
                ),
                voiceInput: _voiceInput,
                voiceOutput: _voiceOutput,
              ),
              onOpenRecovery: _openRecoveryCenter,
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

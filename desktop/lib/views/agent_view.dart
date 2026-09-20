import 'dart:async';
import 'package:flutter/material.dart';
import '../assistant/rowan_action_cue_controller.dart';
import '../client/gateway_client.dart';
import '../controllers/chat_admission_controller.dart';
import '../controllers/chat_context_controller.dart';
import '../models/chat.dart';
import '../models/gateway_models.dart';
import '../navigation/app_route.dart';
import '../services/chat_draft_store.dart';
import '../services/chat_store.dart';
import '../services/settings.dart';
import '../widgets/chat_composer.dart';
import '../widgets/chat_context_status.dart';
import '../widgets/chat_conversation_sheet.dart';
import '../widgets/chat_header.dart';
import '../widgets/chat_sidebar.dart';
import '../widgets/chat_workspace.dart';
import '../widgets/chat_welcome.dart';
import '../widgets/flywheel_nav.dart';
import '../widgets/fw.dart';
import '../widgets/operation_grant_sheet.dart';
import '../widgets/start_task_prelude.dart';
import 'agent_mode_pane.dart';

part 'agent_view_layout.dart';
part 'agent_view_admission.dart';

class AgentView extends StatefulWidget {
  const AgentView({
    super.key,
    required this.client,
    required this.alive,
    required this.settings,
    this.chatStore,
    this.draftStore,
    this.startTaskHandoff,
    this.actionCueController,
  });
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  final ChatStore? chatStore;
  final ChatDraftStore? draftStore;
  final StartTaskHandoff? startTaskHandoff;
  final RowanActionCueController? actionCueController;
  @override
  State<AgentView> createState() => _AgentViewState();
}

class _AgentViewState extends State<AgentView> {
  final _workspace = ChatWorkspaceController();
  final _chosenModels = <String, String>{};
  late final ChatAdmissionController _admission;
  late Conversation _current;
  List<EndpointRow> _endpoints = [];
  String? _model;
  StreamSubscription<Map<String, dynamic>>? _sub;
  Completer<PromptDisposition>? _disposition;
  ChatDraft? _submittedDraft;
  ChatMessage? _assistant;
  final _contextStatus = <String, ChatContextOutcome>{};
  bool _admitting = false, _accepted = false, _streaming = false;
  bool _providerDispatchStarted = false;
  bool _agentMode = false;
  String? _agentSeedGoal;
  int _generation = 0;
  bool get _busy => _admitting || _streaming;
  List<Conversation> get _conversations => _admission.conversations;
  @override
  void initState() {
    super.initState();
    _admission = ChatAdmissionController(
        widget.chatStore ?? ChatStore(), widget.draftStore ?? ChatDraftStore())
      ..restore();
    _current = _conversations.isEmpty
        ? _admission.blankConversation(null)
        : _conversations.first;
    if (_conversations.isEmpty) _conversations.add(_current);
    _model = _current.model;
    _applyStartTaskHandoff(widget.startTaskHandoff, notify: false);
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(AgentView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadEndpoints();
    if (widget.startTaskHandoff != old.startTaskHandoff) {
      _applyStartTaskHandoff(widget.startTaskHandoff, notify: true);
    }
  }

  @override
  void dispose() {
    _generation++;
    _sub?.cancel();
    if (!_providerDispatchStarted && _submittedDraft != null) {
      _admission.retain(_submittedDraft!);
    }
    if (!(_disposition?.isCompleted ?? true)) {
      _disposition!.complete(PromptDisposition.retained);
    }
    _workspace.dispose();
    super.dispose();
  }

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (!mounted) return;
      setState(() {
        _endpoints = rows;
        _model ??= defaultEndpoint(rows)?.name;
        _current.model ??= _model;
      });
    } catch (_) {/* offline empty state owns the presentation */}
  }

  void _newChat() {
    if (_current.isEmpty || _busy) return;
    setState(() {
      _current = _admission.blankConversation(_model);
      _conversations.insert(0, _current);
    });
    _admission.persistHistory();
  }

  void _select(Conversation c) {
    if (identical(c, _current) || _busy) return;
    setState(() {
      _current = c;
      _model = c.model ?? _model;
    });
  }

  void _delete(Conversation c) {
    if (_busy) return;
    setState(() {
      _conversations.remove(c);
      if (identical(c, _current)) {
        _current = _conversations.isEmpty
            ? _admission.blankConversation(_model)
            : _conversations.first;
        if (_conversations.isEmpty) _conversations.add(_current);
      }
    });
    _admission.persistHistory();
  }

  void _draftChanged(String text) => _admission.changeDraft(_current, text);

  void _refresh(VoidCallback fn) => setState(fn);

  void _applyStartTaskHandoff(StartTaskHandoff? handoff,
      {required bool notify}) {
    final text = handoff?.text.trim();
    if (text == null || text.isEmpty || _busy) return;
    final existingDraft = _admission.draftText(_current).trim();
    if (_current.isEmpty && existingDraft == text) return;
    void apply() {
      if (!_current.isEmpty || existingDraft.isNotEmpty) {
        _current = _admission.blankConversation(_model);
        _conversations.insert(0, _current);
      }
      _admission.changeDraft(_current, text);
      _agentMode = false;
      _agentSeedGoal = null;
    }

    if (notify && mounted) {
      setState(apply);
    } else {
      apply();
    }
  }

  Future<PromptDisposition> _send(String text) {
    const retained = PromptDisposition.retained;
    if (_busy) return Future.value(retained);
    final reconciled = _admission.reconcileAdmitted(_current, text);
    if (reconciled != null) {
      setState(() {});
      return Future.value(reconciled);
    }
    if (_model == null) return Future.value(retained);
    final submitted = _admission.prepare(_current, text);
    if (submitted == null) return Future.value(retained);
    unawaited(_beginAdmission(submitted));
    return _disposition!.future;
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('Engine offline.', command: 'flywheel up');
    }
    return LayoutBuilder(builder: (context, constraints) {
      final narrow = constraints.maxWidth < 600;
      return Row(children: [
        if (!_agentMode && !narrow)
          ChatSidebar(
              conversations: _conversations,
              current: _current,
              streaming: _busy,
              onNew: _newChat,
              onSelect: _select,
              onDelete: _delete),
        Expanded(
            child: Column(children: [
          _header(showConversations: narrow && !_agentMode),
          Expanded(child: _body()),
          if (!_agentMode)
            ChatContextStatus(outcome: _contextStatus[_current.id]),
          if (!_agentMode && !_current.isEmpty) _composer(),
        ])),
      ]);
    });
  }
}

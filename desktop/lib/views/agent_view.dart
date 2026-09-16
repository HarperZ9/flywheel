import 'dart:async';
import 'package:flutter/material.dart';
import '../assistant/rowan_action_cue_controller.dart';
import '../client/gateway_client.dart';
import '../controllers/chat_admission_controller.dart';
import '../models/chat.dart';
import '../models/gateway_models.dart';
import '../navigation/app_route.dart';
import '../services/chat_draft_store.dart';
import '../services/chat_store.dart';
import '../services/settings.dart';
import '../widgets/chat_composer.dart';
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
  bool _admitting = false, _accepted = false, _streaming = false;
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

  Future<void> _beginAdmission(ChatDraft submitted) async {
    final generation = ++_generation;
    _submittedDraft = submitted;
    _assistant = null;
    _accepted = false;
    _admitting = true;
    _disposition = Completer<PromptDisposition>();
    setState(() {});
    final endpoint = _model!;
    final chosen = _chosenModels[endpoint];
    final model = chosen == null ? endpoint : '$endpoint:$chosen';
    final wire = _current.messages.map((message) => message.toWire()).toList();
    wire.add({'role': 'user', 'content': submitted.text});
    final operation = GatewayOperation.chat(submitted.attemptRef!, model, wire,
        dataRefs: const [], credentialRefs: const []);
    await authorizeGatewayStream(context, operation, (body) {
      _sub = widget.client.chatStream(wire, model, authorizedBody: body).listen(
          (event) => _onEvent(generation, event),
          onError: (_) => _onObservationClosed(generation),
          onDone: () => _onObservationClosed(generation));
    }, () => _onObservationClosed(generation),
        currentOperation: () => _model == endpoint &&
                _chosenModels[endpoint] == chosen &&
                _admission.draftText(_current) == submitted.text
            ? operation
            : null);
  }

  void _onEvent(int generation, Map<String, dynamic> event) {
    if (!mounted || generation != _generation || !_validEvent(event)) return;
    if (_assistant == null) {
      _acceptFirstEvent(event);
    } else if (_accepted) {
      _applyEvent(_assistant!, event);
    }
    if (_accepted) _scrollToEnd();
  }

  void _acceptFirstEvent(Map<String, dynamic> event) {
    final assistant = ChatMessage(
        role: 'assistant',
        streaming: true,
        attemptRef: _submittedDraft!.attemptRef);
    _applyEvent(assistant, event);
    final decision =
        _admission.acceptFirst(_current, _submittedDraft!, assistant);
    _accepted = decision.visible;
    _assistant = assistant;
    _streaming = decision.visible;
    _finishDisposition(decision.disposition);
  }

  void _applyEvent(ChatMessage assistant, Map<String, dynamic> event) {
    if (event['type'] == 'delta') {
      assistant.text += event['content'] as String;
    } else {
      assistant.setReceipt(event['receipt'] as Map<String, dynamic>?);
    }
  }

  void _onObservationClosed(int generation) {
    if (!mounted || generation != _generation) return;
    if (_assistant == null) {
      _admission.retain(_submittedDraft!);
      _finishDisposition(PromptDisposition.retained);
      return;
    }
    if (!_accepted) return;
    setState(() {
      _assistant!.streaming = false;
      if (_assistant!.receipt == null) {
        const unknown = 'Reply interrupted; completion is unknown.';
        _assistant!.text = _assistant!.text.isEmpty
            ? unknown
            : '${_assistant!.text}\n\n$unknown';
      }
      _streaming = false;
    });
    _admission.persistHistory();
  }

  void _finishDisposition(PromptDisposition result) {
    _admitting = false;
    if (!(_disposition?.isCompleted ?? true)) _disposition!.complete(result);
    if (mounted) setState(() {});
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
          if (!_agentMode && !_current.isEmpty) _composer(),
        ])),
      ]);
    });
  }
}

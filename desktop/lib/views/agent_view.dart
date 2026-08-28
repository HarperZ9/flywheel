import 'dart:async';
import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../controllers/chat_admission_controller.dart';
import '../models/chat.dart';
import '../models/gateway_models.dart';
import '../services/chat_draft_store.dart';
import '../services/chat_store.dart';
import '../services/settings.dart';
import '../widgets/chat_composer.dart';
import '../widgets/chat_header.dart';
import '../widgets/chat_sidebar.dart';
import '../widgets/chat_thread.dart';
import '../widgets/chat_welcome.dart';
import '../widgets/fw.dart';
import '../widgets/operation_grant_sheet.dart';
import 'agent_mode_pane.dart';

class AgentView extends StatefulWidget {
  const AgentView({
    super.key,
    required this.client,
    required this.alive,
    required this.settings,
    this.chatStore,
    this.draftStore,
  });
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  final ChatStore? chatStore;
  final ChatDraftStore? draftStore;
  @override
  State<AgentView> createState() => _AgentViewState();
}

class _AgentViewState extends State<AgentView> {
  final _scroll = ScrollController();
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
        ? _admission.blankConversation(null) : _conversations.first;
    if (_conversations.isEmpty) _conversations.add(_current);
    _model = _current.model;
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(AgentView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadEndpoints();
  }

  @override
  void dispose() {
    _generation++;
    _sub?.cancel();
    if (!(_disposition?.isCompleted ?? true)) {
      _disposition!.complete(PromptDisposition.retained);
    }
    _scroll.dispose();
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
    setState(() { _current = c; _model = c.model ?? _model; });
  }

  void _delete(Conversation c) {
    if (_busy) return;
    setState(() {
      _conversations.remove(c);
      if (identical(c, _current)) {
        _current = _conversations.isEmpty
            ? _admission.blankConversation(_model) : _conversations.first;
        if (_conversations.isEmpty) _conversations.add(_current);
      }
    });
    _admission.persistHistory();
  }

  void _draftChanged(String text) => _admission.changeDraft(_current, text);
  Future<PromptDisposition> _send(String text) {
    const retained = PromptDisposition.retained;
    if (_busy) return Future.value(retained);
    final reconciled = _admission.reconcileAdmitted(_current, text);
    if (reconciled != null) { setState(() {}); return Future.value(reconciled); }
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

  void _scrollToEnd() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
      });
  void _showConversations() => showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        constraints: const BoxConstraints(maxWidth: 400),
        builder: (_) => DraggableScrollableSheet(
          initialChildSize: 0.55, minChildSize: 0.3, maxChildSize: 0.85,
          expand: false,
          builder: (sc, ctrl) => ChatSidebar(
            conversations: _conversations,
            current: _current, streaming: _busy, scrollController: ctrl,
            onNew: () { _newChat(); Navigator.of(sc).pop(); },
            onSelect: (c) { _select(c); Navigator.of(sc).pop(); },
            onDelete: _delete,
          ),
        ),
      );

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
          if (!_agentMode) _composer(),
        ])),
      ]);
    });
  }

  Widget _header({bool showConversations = false}) => ChatHeader(
      agentMode: _agentMode, streaming: _busy, endpoints: _endpoints,
      endpoint: _model, chosenModel: _chosenModels[_model],
      onMode: (v) => setState(() => _agentMode = v),
      onEndpoint: (v) => setState(() => _model = v),
      onModel: (v) => setState(() => v.isEmpty
          ? _chosenModels.remove(_model) : _chosenModels[_model!] = v),
      onShowConversations: showConversations ? _showConversations : null,
      loadModels: () => widget.client.models(_model ?? ''));
  Widget _body() => _agentMode
      ? AgentModePane(
          client: widget.client, alive: widget.alive, settings: widget.settings)
      : _current.isEmpty
          ? const ChatWelcome()
          : ChatThread(messages: _current.messages, controller: _scroll);

  Widget _composer() => ChatComposer(
      key: ValueKey(_current.id),
      streaming: _streaming,
      initialText: _admission.draftText(_current),
      onDraftChanged: _draftChanged,
      onSend: _send,
      savedPrompts: widget.settings.savedPrompts,
      onSavePrompt: (text) => setState(() => widget.settings.savePrompt(text)));
}

bool _validEvent(Map<String, dynamic> event) => switch (event) {
      {'type': 'delta', 'content': final String value} => value.isNotEmpty,
      {'type': 'done', 'receipt': final Map<String, dynamic> _} => true,
      _ => false,
    };

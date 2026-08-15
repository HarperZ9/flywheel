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
  Conversation? _submittedConversation;
  ChatDraft? _submittedDraft;
  ChatMessage? _assistant;
  bool _admitting = false;
  bool _accepted = false;
  bool _streaming = false;
  bool _agentMode = false;
  int _generation = 0;

  bool get _busy => _admitting || _streaming;
  List<Conversation> get _conversations => _admission.conversations;

  @override
  void initState() {
    super.initState();
    _admission = ChatAdmissionController(
        widget.chatStore ?? ChatStore(), widget.draftStore ?? ChatDraftStore());
    _admission.restore();
    _current = _conversations.isEmpty
        ? _admission.blankConversation(null)
        : _conversations.first;
    if (_conversations.isEmpty) _conversations.add(_current);
    _model = _current.model;
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(AgentView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.alive && widget.alive) _loadEndpoints();
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

  void _select(Conversation conversation) {
    if (identical(conversation, _current) || _busy) return;
    setState(() {
      _current = conversation;
      _model = conversation.model ?? _model;
    });
  }

  void _delete(Conversation conversation) {
    if (_busy) return;
    setState(() {
      _conversations.remove(conversation);
      if (identical(conversation, _current)) {
        _current = _conversations.isEmpty
            ? _admission.blankConversation(_model)
            : _conversations.first;
        if (_conversations.isEmpty) _conversations.add(_current);
      }
    });
    _admission.persistHistory();
  }

  void _draftChanged(String text) => _admission.changeDraft(_current, text);

  Future<PromptDisposition> _send(String text) {
    if (_busy || _model == null) {
      return Future.value(PromptDisposition.retained);
    }
    final submitted = _admission.prepare(_current, text);
    if (submitted == null) return Future.value(PromptDisposition.retained);
    _beginAdmission(submitted);
    return _disposition!.future;
  }

  void _beginAdmission(ChatDraft submitted) {
    final generation = ++_generation;
    _submittedDraft = submitted;
    _submittedConversation = _current;
    _assistant = null;
    _accepted = false;
    _admitting = true;
    _disposition = Completer<PromptDisposition>();
    setState(() {});
    final chosen = _chosenModels[_model];
    final model = chosen == null ? _model! : '$_model:$chosen';
    final wire = _current.messages.map((message) => message.toWire()).toList();
    wire.add({'role': 'user', 'content': submitted.text});
    _sub = widget.client.chatStream(wire, model).listen(
        (event) => _onEvent(generation, event),
        onError: (_) => _onTerminal(generation),
        onDone: () => _onTerminal(generation));
  }

  void _onEvent(int generation, Map<String, dynamic> event) {
    if (!mounted || generation != _generation || !_validEvent(event)) return;
    if (!_accepted) {
      if (!_acceptFirstEvent(event)) return;
    } else {
      _applyEvent(_assistant!, event);
    }
    _scrollToEnd();
  }

  bool _acceptFirstEvent(Map<String, dynamic> event) {
    final assistant = ChatMessage(role: 'assistant', streaming: true);
    _applyEvent(assistant, event);
    final decision = _admission.acceptFirst(
        _submittedConversation!, _submittedDraft!, assistant);
    _accepted = decision.visible;
    _assistant = assistant;
    _streaming = decision.visible;
    _finishDisposition(decision.disposition);
    return decision.visible;
  }

  void _applyEvent(ChatMessage assistant, Map<String, dynamic> event) {
    if (event['type'] == 'delta') {
      assistant.text += event['content'] as String;
    } else {
      assistant.setReceipt(event['receipt'] as Map<String, dynamic>?);
    }
  }

  void _onTerminal(int generation) {
    if (!mounted || generation != _generation) return;
    if (!_accepted) {
      _retainAdmission();
      return;
    }
    setState(() {
      _assistant!.streaming = false;
      if (_assistant!.text.isEmpty) _assistant!.text = 'No reply arrived.';
      _streaming = false;
    });
    _admission.persistHistory();
  }

  void _retainAdmission() {
    _admission.retain(_submittedDraft!);
    _finishDisposition(PromptDisposition.retained);
  }

  void _finishDisposition(PromptDisposition result) {
    _admitting = false;
    if (!(_disposition?.isCompleted ?? true)) _disposition!.complete(result);
    if (mounted) setState(() {});
  }

  void _stop() {
    _sub?.cancel();
    for (final message in _current.messages) {
      message.streaming = false;
    }
    setState(() => _streaming = false);
  }

  void _scrollToEnd() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.animateTo(_scroll.position.maxScrollExtent,
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut);
        }
      });

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline. Chat appears when it runs.',
          command: 'flywheel up');
    }
    return Row(children: [
      if (!_agentMode)
        ChatSidebar(
            conversations: _conversations,
            current: _current,
            streaming: _busy,
            onNew: _newChat,
            onSelect: _select,
            onDelete: _delete),
      Expanded(
          child: Column(children: [
        _header(),
        Expanded(child: _body()),
        if (!_agentMode) _composer(),
      ])),
    ]);
  }

  Widget _header() => ChatHeader(
      agentMode: _agentMode,
      streaming: _busy,
      endpoints: _endpoints,
      endpoint: _model,
      chosenModel: _chosenModels[_model],
      onMode: (value) => setState(() => _agentMode = value),
      onEndpoint: (value) => setState(() => _model = value),
      onModel: (value) => setState(() => value.isEmpty
          ? _chosenModels.remove(_model)
          : _chosenModels[_model!] = value),
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
      onStop: _stop,
      hint: _model == null ? 'No model available…' : 'Message ${_model!}…',
      savedPrompts: widget.settings.savedPrompts,
      onSavePrompt: (text) => setState(() => widget.settings.savePrompt(text)));
}

bool _validEvent(Map<String, dynamic> event) =>
    (event['type'] == 'delta' &&
        event['content'] is String &&
        (event['content'] as String).isNotEmpty) ||
    (event['type'] == 'done' && event['receipt'] is Map<String, dynamic>);

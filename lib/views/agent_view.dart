// agent_view.dart — the Chat surface. A real, multi-turn conversation with any
// endpoint in the roster: streamed replies, a history of past chats, a model
// picker, and — quietly, under each turn — the re-derivable receipt that makes
// this a Flywheel chat and not just another box. The conversation is the subject;
// the accountability is the guarantee underneath.

import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/chat.dart';
import '../models/gateway_models.dart';
import '../services/chat_store.dart';
import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import 'agent_mode_pane.dart';
import '../widgets/chat_composer.dart';
import '../widgets/chat_sidebar.dart';
import '../widgets/chat_thread.dart';
import '../widgets/fw.dart';
import '../widgets/mode_chip.dart';
import '../widgets/model_picker.dart';

class AgentView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  const AgentView(
      {super.key,
      required this.client,
      required this.alive,
      required this.settings});

  @override
  State<AgentView> createState() => _AgentViewState();
}

class _AgentViewState extends State<AgentView> {
  final List<Conversation> _conversations = [];
  late Conversation _current;
  final _store = ChatStore();
  final _scroll = ScrollController();
  List<EndpointRow> _endpoints = [];
  String? _model;
  bool _streaming = false;
  bool _agentMode = false;
  StreamSubscription? _sub;
  int _seq = 0;

  @override
  void initState() {
    super.initState();
    final saved = _store.load();
    if (saved.isNotEmpty) {
      _conversations.addAll(saved);
      _current = saved.first;
    } else {
      _current = _blankConversation();
      _conversations.add(_current);
    }
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(AgentView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadEndpoints();
  }

  @override
  void dispose() {
    _sub?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  Conversation _blankConversation() =>
      Conversation(id: 'c${_seq++}', model: _model);

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (mounted) {
        setState(() {
          _endpoints = rows;
          _model ??= rows.isNotEmpty ? rows.first.name : null;
          _current.model ??= _model;
        });
      }
    } catch (_) {/* offline empty-state handles it */}
  }

  void _newChat() {
    if (_current.isEmpty) return; // already on a fresh one
    setState(() {
      _current = _blankConversation();
      _conversations.insert(0, _current);
    });
    _store.save(_conversations);
  }

  void _select(Conversation c) {
    if (identical(c, _current) || _streaming) return;
    setState(() => _current = c);
  }

  void _delete(Conversation c) {
    setState(() {
      _conversations.remove(c);
      if (identical(c, _current)) {
        if (_conversations.isEmpty) {
          _current = _blankConversation();
          _conversations.add(_current);
        } else {
          _current = _conversations.first;
        }
      }
    });
    _store.save(_conversations);
  }

  void _send(String text) {
    if (_model == null) return;
    final assistant = ChatMessage(role: 'assistant', streaming: true);
    setState(() {
      _current.model ??= _model;
      _current.messages.add(ChatMessage(role: 'user', text: text));
      _current.messages.add(assistant);
      _streaming = true;
    });
    _current.titleFromFirstMessage();
    _scrollToEnd();

    final wire = _current.messages
        .where((m) => !(m.streaming && m.text.isEmpty))
        .map((m) => m.toWire())
        .toList();
    _sub = widget.client.chatStream(wire, _model!).listen(
      (e) {
        if (!mounted) return;
        setState(() {
          if (e['type'] == 'delta') {
            assistant.text += e['content'] as String;
          } else if (e['type'] == 'done') {
            assistant.receipt = e['receipt'] as Map<String, dynamic>?;
          }
        });
        _scrollToEnd();
      },
      onError: (_) => _finish(assistant, failed: true),
      onDone: () => _finish(assistant),
    );
  }

  void _finish(ChatMessage assistant, {bool failed = false}) {
    if (!mounted) return;
    setState(() {
      assistant.streaming = false;
      // a run that produced nothing (an error, or an endpoint with no live model)
      // reads as a plain message, never a blank bubble the user has to guess at.
      if (assistant.text.isEmpty) {
        assistant.text = 'No reply arrived. The endpoint may be offline or have no '
            'model loaded. Pick another model above, or check Endpoints.';
      }
      _streaming = false;
    });
    _store.save(_conversations); // the completed turn survives a restart
  }

  void _stop() {
    _sub?.cancel();
    for (final m in _current.messages) {
      m.streaming = false;
    }
    setState(() => _streaming = false);
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 180), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline. Chat appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return Row(children: [
      if (!_agentMode)
        ChatSidebar(
          conversations: _conversations,
          current: _current,
          streaming: _streaming,
          onNew: _newChat,
          onSelect: _select,
          onDelete: _delete,
        ),
      Expanded(
        child: Column(children: [
          _header(t),
          Expanded(
            child: _agentMode
                ? AgentModePane(
                    client: widget.client,
                    alive: widget.alive,
                    settings: widget.settings)
                : _current.isEmpty
                    ? _welcome(t)
                    : ChatThread(
                        messages: _current.messages, controller: _scroll),
          ),
          if (!_agentMode)
            ChatComposer(
              streaming: _streaming,
              onSend: _send,
              onStop: _stop,
              hint:
                  _model == null ? 'No model available…' : 'Message ${_model!}…',
              savedPrompts: widget.settings.savedPrompts,
              onSavePrompt: (t) =>
                  setState(() => widget.settings.savePrompt(t)),
            ),
        ]),
      ),
    ]);
  }

  Widget _header(FwTokens t) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s5, vertical: FwLayout.s3),
        decoration:
            BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(children: [
          Text('Chat', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(width: FwLayout.s4),
          FwModeChip(
              label: 'chat',
              active: !_agentMode,
              onTap: () {
                if (!_streaming) setState(() => _agentMode = false);
              }),
          const SizedBox(width: FwLayout.s1),
          FwModeChip(
              label: 'agent',
              active: _agentMode,
              onTap: () {
                if (!_streaming) setState(() => _agentMode = true);
              }),
          const SizedBox(width: FwLayout.s4),
          if (!_agentMode && _endpoints.isNotEmpty)
            ModelPickerButton(
              endpoints: _endpoints,
              current: _model,
              enabled: !_streaming,
              onSelect: (v) => setState(() => _model = v),
            ),
          const Spacer(),
          Icon(Icons.verified_outlined, size: 13, color: t.inkFaint),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
                _agentMode
                    ? 'every run persists with its trace'
                    : 'every reply is witnessed',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ),
        ]),
      );

  Widget _welcome(FwTokens t) => Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.auto_awesome_outlined, size: 30, color: t.verified),
            const SizedBox(height: FwLayout.s4),
            Text('What are we working on?',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: FwLayout.s2),
            Text(
              'Ask anything. Every answer runs on the model you pick and carries a '
              'receipt you can re-check. The trust is built in, never in the way.',
              textAlign: TextAlign.center,
              style: TextStyle(color: t.inkFaint, fontSize: 13.5, height: 1.5),
            ),
          ]),
        ),
      );
}

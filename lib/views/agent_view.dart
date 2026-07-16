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
import '../theme/flywheel_theme.dart';
import '../widgets/chat_composer.dart';
import '../widgets/chat_thread.dart';
import '../widgets/fw.dart';

class AgentView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const AgentView({super.key, required this.client, required this.alive});

  @override
  State<AgentView> createState() => _AgentViewState();
}

class _AgentViewState extends State<AgentView> {
  final List<Conversation> _conversations = [];
  late Conversation _current;
  final _scroll = ScrollController();
  List<EndpointRow> _endpoints = [];
  String? _model;
  bool _streaming = false;
  StreamSubscription? _sub;
  int _seq = 0;

  @override
  void initState() {
    super.initState();
    _current = _blankConversation();
    _conversations.add(_current);
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
  }

  void _select(Conversation c) {
    if (identical(c, _current) || _streaming) return;
    setState(() => _current = c);
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
            'model loaded — pick another model above, or check Endpoints.';
      }
      _streaming = false;
    });
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
      _sidebar(t),
      Expanded(
        child: Column(children: [
          _header(t),
          Expanded(
            child: _current.isEmpty
                ? _welcome(t)
                : ChatThread(messages: _current.messages, controller: _scroll),
          ),
          ChatComposer(
            streaming: _streaming,
            onSend: _send,
            onStop: _stop,
            hint: _model == null ? 'No model available…' : 'Message ${_model!}…',
          ),
        ]),
      ),
    ]);
  }

  Widget _sidebar(FwTokens t) => Container(
        width: 232,
        decoration: BoxDecoration(
          color: t.ground2,
          border: Border(right: BorderSide(color: t.hairline)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Padding(
            padding: const EdgeInsets.all(FwLayout.s3),
            child: OutlinedButton.icon(
              onPressed: _streaming ? null : _newChat,
              icon: const Icon(Icons.add_rounded, size: 16),
              label: const Text('New chat'),
              style: OutlinedButton.styleFrom(
                  alignment: Alignment.centerLeft,
                  padding: const EdgeInsets.symmetric(
                      horizontal: FwLayout.s3, vertical: FwLayout.s3)),
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: FwLayout.s2),
              children: [
                for (final c in _conversations)
                  _ConvItem(
                    title: c.isEmpty ? 'New chat' : c.title,
                    selected: identical(c, _current),
                    onTap: () => _select(c),
                  ),
              ],
            ),
          ),
        ]),
      );

  Widget _header(FwTokens t) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s5, vertical: FwLayout.s3),
        decoration:
            BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(children: [
          Text('Chat', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(width: FwLayout.s4),
          if (_endpoints.isNotEmpty)
            DropdownButton<String>(
              value: _model,
              underline: const SizedBox(),
              isDense: true,
              borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
              style: fwMono(t, size: 12.5, color: t.inkSoft),
              items: [
                for (final e in _endpoints)
                  DropdownMenuItem(
                    value: e.name,
                    child: Text('${e.name}${e.hasCredential ? '' : '  (no key)'}'),
                  ),
              ],
              onChanged:
                  _streaming ? null : (v) => setState(() => _model = v),
            ),
          const Spacer(),
          Icon(Icons.verified_outlined, size: 13, color: t.inkFaint),
          const SizedBox(width: 5),
          Text('every reply is witnessed',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
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
              'receipt you can re-check — the trust is built in, never in the way.',
              textAlign: TextAlign.center,
              style: TextStyle(color: t.inkFaint, fontSize: 13.5, height: 1.5),
            ),
          ]),
        ),
      );
}

class _ConvItem extends StatelessWidget {
  final String title;
  final bool selected;
  final VoidCallback onTap;
  const _ConvItem(
      {required this.title, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Material(
      color: selected ? t.panel : Colors.transparent,
      borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        child: Padding(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s3, vertical: 9),
          child: Text(title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontSize: 13,
                  color: selected ? t.ink : t.inkMuted,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400)),
        ),
      ),
    );
  }
}

// academy_view.dart -- the curriculum derived from the live code, rendered
// as the arc it is: foundations before composition, every lesson pinned
// to its source hash, every check runnable, absence shown not papered.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class AcademyView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const AcademyView({super.key, required this.client, required this.alive});

  @override
  State<AcademyView> createState() => _AcademyViewState();
}

class _AcademyViewState extends State<AcademyView> {
  Map<String, dynamic>? _doc;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!widget.alive || _loading) return;
    setState(() => _loading = true);
    try {
      final doc = await widget.client.academy();
      if (mounted) setState(() => _doc = doc);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The curriculum appears when it runs.',
          command: 'flywheel up');
    }
    if (_error != null) return FwEmpty('Curriculum unavailable: $_error');
    if (_doc == null) return const Center(child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)));
    return SingleChildScrollView(
      padding: const EdgeInsets.all(FwLayout.s5),
      child: AcademyArc(_doc!),
    );
  }
}

/// Pure renderer for the curriculum document; testable without a gateway.
class AcademyArc extends StatelessWidget {
  final Map<String, dynamic> doc;
  const AcademyArc(this.doc, {super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final lessons = ((doc['lessons'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('the academy arc'),
        const SizedBox(height: FwLayout.s4),
        for (var i = 0; i < lessons.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s3),
            child: HairlineCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    VerdictDot((lessons[i]['present'] ?? false) == true
                        ? 'verified'
                        : 'unverifiable'),
                    const SizedBox(width: FwLayout.s2),
                    Text(
                        '${i + 1}. ${lessons[i]['title'] ?? ''}'
                        '${((lessons[i]['prereqs'] ?? []) as List).isEmpty ? '' : '  <- ${((lessons[i]['prereqs']) as List).join(', ')}'}',
                        style: fwMono(t, size: 12).copyWith(color: t.ink)),
                  ]),
                  const SizedBox(height: FwLayout.s2),
                  Text('${lessons[i]['teach'] ?? ''}',
                      style:
                          fwMono(t, size: 11.5).copyWith(color: t.inkSoft)),
                  const SizedBox(height: FwLayout.s2),
                  Text(
                      'check: ${(lessons[i]['check'] ?? const {})['method'] ?? ''} '
                      '${(lessons[i]['check'] ?? const {})['path'] ?? ''} '
                      '-> ${(lessons[i]['check'] ?? const {})['expect'] ?? ''}',
                      style:
                          fwMono(t, size: 11).copyWith(color: t.inkMuted)),
                  if ('${lessons[i]['source_sha256'] ?? ''}'.isNotEmpty)
                    HashText('source', '${lessons[i]['source_sha256']}',
                        keep: 16),
                ],
              ),
            ),
          ),
        if ('${doc['completion_flow'] ?? ''}'.isNotEmpty)
          HonestNull('${doc['completion_flow']}'),
        if ('${doc['attribution'] ?? ''}'.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text('${doc['attribution']}',
              style: fwMono(t, size: 10.5).copyWith(color: t.inkFaint)),
        ],
      ],
    );
  }
}

// composer_results.dart — the shared shape for every "build a thing, read the
// result" view: a header, then a draggable vertical split with the composer
// on top and the results below, each scrolling on its own. The results pane
// grows independently of the form, and the divider position persists per view.
// This is the resizability the audit named for science, workflows, plan, and
// discourse, done once.

import 'package:flutter/material.dart';

import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import 'split_pane.dart';

class ComposerResults extends StatelessWidget {
  final Widget header;
  final Widget composer;
  final List<Widget> results;
  final DesktopSettings settings;
  final String viewKey; // persists the divider fraction

  /// Shown in the results pane before the first run: an empty state, not a
  /// blank. When null a plain hint renders.
  final Widget? placeholder;
  const ComposerResults(
      {super.key,
      required this.header,
      required this.composer,
      required this.results,
      required this.settings,
      required this.viewKey,
      this.placeholder});

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(
            FwLayout.s6, FwLayout.s5, FwLayout.s6, FwLayout.s3),
        child: header,
      ),
      Expanded(
        child: SplitPane(
          axis: Axis.vertical,
          initialFraction: settings.splitFraction(viewKey, 0.42),
          minFraction: 0.15,
          maxFraction: 0.8,
          onFraction: (f) => settings.setSplitFraction(viewKey, f),
          first: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(
                FwLayout.s6, 0, FwLayout.s6, FwLayout.s4),
            child: composer,
          ),
          second: results.isEmpty
              ? (placeholder ??
                  Center(
                      child: Text('Run it to see the result here.',
                          style: TextStyle(
                              fontSize: 12.5,
                              color: context.fw.inkFaint))))
              : SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(FwLayout.s6, FwLayout.s4,
                      FwLayout.s6, FwLayout.s6),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: results),
                ),
        ),
      ),
    ]);
  }
}

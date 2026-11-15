"""Check the publish dependency graph against a failed native build.

This covers the workflow's static fail-closed wiring, not a hosted CI execution.
"""
import re

from claude_plugin_helpers import ROOT


def jobs():
    workflow = (ROOT / '.github/workflows/publish.yml').read_text(encoding='utf-8')
    return dict(re.findall(r'(?ms)^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)', workflow))


def dependencies(body):
    match = re.search(r'^    needs: (.+)$', body, re.M)
    return set(re.findall(r'[\w-]+', match[1])) if match else set()


def test_native_failure_blocks_both_external_write_jobs():
    graph = jobs()
    assert 'native-build' in graph
    failed = {'native-build'}
    for _ in graph:
        failed.update(name for name, body in graph.items() if dependencies(body) & failed)
    assert {'publish', 'attach-plugin'} <= failed
    for name in ('native-build', 'publish', 'attach-plugin'):
        assert 'continue-on-error:' not in graph[name]
        assert 'always()' not in graph[name]
    native = graph['native-build']
    assert 'windows-latest' in native
    assert 'build_native_articulate.py' in native and '--mode release' in native


def test_native_and_source_plugin_assets_have_distinct_artifact_channels():
    graph = jobs()
    native, source, attach = graph['native-build'], graph['plugin-build'], graph['attach-plugin']
    assert 'name: native-dist' in native
    assert 'name: plugin-dist' in source
    assert 'archive_claude_plugin.py' in source and 'build_native_articulate.py' not in source
    assert 'name: native-dist' in attach and 'name: plugin-dist' in attach
    assert 'native-SHA256SUMS.txt' in attach and 'plugin-SHA256SUMS.txt' in attach
    assert '--clobber' not in attach

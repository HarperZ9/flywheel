"""The release must qualify and hash-bind the source MCP companion."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def step(document, name):
    marker = f'      - name: {name}\n'
    body = document.split(marker, 1)[1]
    return re.split(r'\n      - (?:name:|uses:)', body, maxsplit=1)[0]


def test_source_companion_is_qualified_before_installer_candidate_is_staged():
    workflow = (ROOT / '.github/workflows/desktop-release.yml').read_text()
    build = step(workflow, 'Build and qualify the matching source tools plugin')
    assert build.index('build_source_tool_plugin.py --out') < build.index('check_source_tool_plugin.py --archive')
    assert build.index('check_source_tool_plugin.py --archive') < build.index('build_source_tool_plugin.py --verify')
    for failure in ('source plugin build failed', 'source plugin qualification failed',
                    'source plugin hash verification failed'):
        assert f'if ($LASTEXITCODE -ne 0) {{ throw "{failure}" }}' in build
    assert workflow.index('Build and qualify the matching source tools plugin') < workflow.index('Stage the candidate artifact')
    assembly = step(workflow, 'Assemble a stable candidate directory')
    for artifact in ('*.zip', 'source-plugin-SHA256SUMS.txt', 'source-plugin-build-receipt.json'):
        assert f'Copy-Item "$sourceOut/{artifact}" build/windows-release-candidate/source-plugin/' in assembly
    assert 'source-plugin/qualification.json' in assembly


def test_publication_requires_source_checksum_and_uploads_the_same_files():
    workflow = (ROOT / '.github/workflows/windows-publish.yml').read_text()
    declaration = workflow.split('      source_plugin_sha256:\n', 1)[1].split('    secrets:', 1)[0]
    assert 'required: true' in declaration and 'type: string' in declaration
    check = step(workflow, 'Verify the accepted source tools plugin')
    assert 'ACCEPTED_SOURCE_PLUGIN_SHA256: ${{ inputs.source_plugin_sha256 }}' in check
    assert '--verify candidate/source-plugin/source-plugin-SHA256SUMS.txt' in check
    assert '--accepted-sha256 $env:ACCEPTED_SOURCE_PLUGIN_SHA256' in check
    assert 'if ($LASTEXITCODE -ne 0) { throw "source plugin verification failed; refusing to publish" }' in check
    assert workflow.index('Verify the accepted source tools plugin') < workflow.index('Publish the GitHub Release (no-clobber)')
    publish = step(workflow, 'Publish the GitHub Release (no-clobber)')
    assert 'candidate/source-plugin/*.zip' in publish
    assert 'candidate/source-plugin/source-plugin-SHA256SUMS.txt' in publish
    assert '@sourcePlugins $sourceSums' in publish

"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations

EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    'relay': {
        'schema': 'flywheel.bundled-lane-expectation/v1',
        'name': 'relay',
        'version': '0.2.3',
        'source_repo': 'https://github.com/HarperZ9/relay',
        'source_commit': '252e781de7fce6367dca0f293852cc9f22356878',
        'source_path': 'src/relay',
        'source_manifest_sha256': 'sha256:b842b4009816bdd92b60a646b2a717f5331a9461ea608aa82b0b1936db58ea98',
        'descriptor_sha256': 'sha256:39bf78bdbb0b481156e7f8bb155aaf11e1deed493e4af618caa4451fe02e25e0',
        'module': 'relay.local_mcp',
        'callable': 'serve',
        'health_tool': 'relay.status',
        'allowed_tools': ('relay.status',),
    },
    'mneme': {
        'schema': 'flywheel.bundled-lane-expectation/v1',
        'name': 'mneme',
        'version': '0.4.1',
        'source_repo': 'https://github.com/HarperZ9/mneme.git',
        'source_commit': 'd3de14d8caa06373fe42b6cc3023285a1d3550bf',
        'source_path': 'src/mneme',
        'source_manifest_sha256': 'sha256:a0ce0a1f641bd60190477b3cce25a29c487b0f6c75f87277f5904ebeddaa6f17',
        'descriptor_sha256': 'sha256:7b6463189ca3d5ea4ea4d3e840465aa2390921a65b29754a666d33798f251cb6',
        'module': 'mneme.mcp',
        'callable': 'serve',
        'health_tool': 'mneme.status',
        'allowed_tools': ('mneme.status', 'mneme.doctor'),
    },
    'plexus': {
        'schema': 'flywheel.bundled-lane-expectation/v1',
        'name': 'plexus',
        'version': '0.2.1',
        'source_repo': 'https://github.com/HarperZ9/plexus.git',
        'source_commit': '31a86aaf30983c6a7a511d2636e6366fcd2b3f36',
        'source_path': 'src/plexus',
        'source_manifest_sha256': 'sha256:c445ac8ced75fd0224acdadcd818eba1c529c32de743dbe483495708e165de2d',
        'descriptor_sha256': 'sha256:c294cbb6be859e96cd19e2d7f2662677af381251ad63a97590220cc4b53ae867',
        'module': 'plexus.mcp',
        'callable': 'serve',
        'health_tool': 'plexus.status',
        'allowed_tools': ('plexus.status', 'plexus.doctor'),
    },
}


def expected_bundled_lane(name: str) -> dict[str, object]:
    value = EXPECTED_BUNDLED_LANES[name]
    return {**value, "allowed_tools": tuple(value["allowed_tools"])}

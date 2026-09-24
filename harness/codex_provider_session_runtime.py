"""Redacted Codex config inspection, never execution authority by itself.

An effective-config read is not atomic with thread or turn execution. Production
admission also requires an owned launcher, enforced policy and runtime acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass

from .evidence_json import canonical_sha256

_POLICY = {
    'approval_policy': ('on-request', 'approval_policy_mismatch'),
    'approvals_reviewer': ('user', 'approval_reviewer_mismatch'),
    'sandbox_mode': ('read-only', 'sandbox_mismatch'),
    'web_search': ('disabled', 'web_search_enabled'),
}
_ORIGINS = ('model', *_POLICY, 'features.hooks', 'features.apps', 'features.plugins')
_LAYER_VALUES = ('mcp_servers', 'notify', 'project_doc_max_bytes')
_LAYER_FIELDS = {'sessionFlags': (), 'user': ('file',), 'system': ('file',),
                 'project': ('dotCodexFolder',)}
_LIMIT = ('Does not prove execution isolation, authentication, sandbox enforcement, '
          'tool effects, native session readiness, or production runtime admission.')


@dataclass(frozen=True)
class CodexConfigInspection:
    configuration_ready: bool
    config_digest: str
    issues: tuple[str, ...]

    @property
    def admitted(self) -> bool:
        return False

    @property
    def does_not_prove(self) -> str:
        return _LIMIT

    def as_result(self) -> dict:
        return {'schema': 'flywheel.codex-config-inspection/v1',
                'configuration_ready': self.configuration_ready, 'admitted': False,
                'config_digest': self.config_digest, 'issues': list(self.issues),
                'does_not_prove': self.does_not_prove}


def inspect_codex_configuration(client, *, cwd: str, model: str) -> CodexConfigInspection:
    """Read only config methods. Return fixed diagnostics, not raw config/errors."""
    if not all(type(v) is str and v.strip() for v in (cwd, model)):
        return CodexConfigInspection(False, '', ('invalid_inspection_request',))
    try:
        response = client.config_read(cwd=cwd, include_layers=True)
        requirements = client.config_requirements_read()
        # Canonical hashing rejects nonfinite numbers and non-JSON/cyclic values.
        digest = canonical_sha256({'policy': 'codex-managed-read-only/v1',
                                   'requested_model': model, 'cwd': cwd,
                                   'config_response': response, 'requirements': requirements})
        issues = _inspect(response, requirements, model)
        return CodexConfigInspection(not issues, digest, tuple(sorted(set(issues))))
    except Exception:
        # Provider exceptions/configuration may contain secrets or local paths.
        return CodexConfigInspection(False, '', ('configuration_unavailable_or_invalid',))


def _inspect(response, requirements, model):
    if type(response) is not dict or type(response.get('config')) is not dict:
        return ['configuration_missing']
    issues = []
    cfg = response['config']
    if cfg.get('model') != model:
        issues.append('model_mismatch')
    for field, (value, issue) in _POLICY.items():
        if cfg.get(field) != value:
            issues.append(issue)
    features = cfg.get('features')
    if type(features) is not dict or any(features.get(k) is not False
                                         for k in ('hooks', 'apps', 'plugins')):
        issues.append('extension_policy_mismatch')
    servers = cfg.get('mcp_servers')
    if type(servers) is not dict:
        issues.append('external_mcp_unknown')
    elif any(type(v) is not dict or v.get('enabled') is not False for v in servers.values()):
        # Empty session overrides are merged, so inspect the resolved server map.
        issues.append('external_mcp_enabled')
    if cfg.get('notify') != []:
        issues.append('notify_enabled')
    if type(cfg.get('project_doc_max_bytes')) is not int or cfg['project_doc_max_bytes'] != 0:
        issues.append('project_instructions_enabled')
    if any(cfg.get(k) is not None for k in
           ('hooks', 'default_permissions', 'experimental_instructions_file')):
        issues.append('unreviewed_execution_settings')
    issues.extend(_provenance_issues(response))
    if type(requirements) is not dict or 'requirements' not in requirements:
        issues.append('managed_requirements_missing')
    elif set(requirements) != {'requirements'} or requirements['requirements'] not in (None, {}):
        issues.append('managed_requirements_unreviewed')
    return issues


def _provenance_issues(response):
    layers, origins = response.get('layers'), response.get('origins')
    if type(layers) is not list or not layers or type(origins) is not dict:
        return ['layer_provenance_missing']
    issues, observed, active, active_configs = [], set(), set(), []
    for layer in layers:
        if type(layer) is not dict or type(layer.get('config')) is not dict:
            issues.append('layer_provenance_invalid')
            continue
        name, version = layer.get('name'), layer.get('version')
        identity = _layer_identity(name, version)
        if identity is None:
            issues.append('layer_provenance_invalid')
            continue
        if identity in observed:
            issues.append('duplicate_config_layer')
        observed.add(identity)
        disabled = layer.get('disabledReason')
        if disabled is not None and (type(disabled) is not str or not disabled.strip()):
            issues.append('layer_provenance_invalid')
        if not disabled:
            active.add(identity)
            active_configs.append(layer['config'])
            if name['type'] == 'project':
                issues.append('active_project_config')
    for key in _ORIGINS:
        origin = origins.get(key)
        if type(origin) is not dict:
            issues.append('policy_origin_missing')
        elif _layer_identity(origin.get('name'), origin.get('version')) not in active:
            issues.append('policy_origin_unobserved')
    for key in _LAYER_VALUES:
        # Installed Codex emits leaf origins; empty maps/lists have no leaf.
        # Require an explicit matching value in an observed active layer too.
        value = response['config'].get(key)
        if not any(key in cfg and type(cfg[key]) is type(value) and cfg[key] == value
                   for cfg in active_configs):
            issues.append('policy_layer_value_missing')
        if key in origins:
            origin = origins[key]
            if type(origin) is not dict or _layer_identity(
                    origin.get('name'), origin.get('version')) not in active:
                issues.append('policy_origin_unobserved')
    return issues


def _layer_identity(name, version):
    if type(name) is not dict or type(version) is not str or not version.strip():
        return None
    kind = name.get('type')
    if type(kind) is not str or kind not in _LAYER_FIELDS:
        return None
    if any(type(name.get(k)) is not str or not name[k].strip() for k in _LAYER_FIELDS[kind]):
        return None
    return canonical_sha256({'name': name, 'version': version})

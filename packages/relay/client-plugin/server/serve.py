"""Local client adapter. No service, model, installation or implicit grant."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import urlsplit

TOOL = 'relay'
if not getattr(sys, 'frozen', False):
    SOURCE = Path(__file__).resolve().parent / 'src'
    if not (SOURCE / TOOL / 'local_mcp.py').is_file():
        sys.stderr.write(f'{TOOL}: the server code is missing from the plugin folder. Reinstall the plugin.\n')
        raise SystemExit(1)
    sys.path.insert(0, str(SOURCE))


def explicit_path(value, *, directory=False):
    path = Path(value or '')
    if not value or not path.is_absolute():
        raise ValueError('an explicit absolute local path is required')
    for part in [path, *path.parents]:
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0)
                                & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('linked path components are not accepted')
    if directory and not path.is_dir():
        raise ValueError('launch root must be an existing directory')
    if not directory and (not path.parent.is_dir() or path.is_dir()):
        raise ValueError('state must name a file in an existing directory')
    return str(path)


HOSTED_KEY_ENV = 'RELAY_API_KEY'


def unset(value):
    """A host that leaves an optional setting unfilled passes its placeholder."""
    return '' if value.startswith('${user_config.') else value.strip()


def hosted_environment(provider, base_url, model):
    """Clear ambient hosted-model keys, gateway URLs and model names, then set only
    the provider the launch names. The key arrives in RELAY_API_KEY, never argv."""
    from relay.endpoints import PROVIDERS
    key = unset(os.environ.pop(HOSTED_KEY_ENV, ''))
    provider, base_url, model = unset(provider), unset(base_url), unset(model)
    for name, spec in PROVIDERS.items():
        up = name.upper()
        for var in (spec['key'], f'{up}_PROVIDER_BASE_URL', f'{up}_PROVIDER_KEY',
                    f'{up}_CLOUD_BASE_URL', f'{up}_CLOUD_KEY', f'{up}_MODEL'):
            os.environ.pop(var, None)
    if not provider:
        if base_url or model:
            raise ValueError('a hosted model URL or name needs a hosted provider')
        return
    if provider not in PROVIDERS:
        raise ValueError('hosted provider must be one of: ' + ', '.join(PROVIDERS))
    up = provider.upper()
    if base_url:
        parts = urlsplit(base_url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise ValueError('hosted model URL must be an http or https URL')
        os.environ[f'{up}_PROVIDER_BASE_URL'] = base_url.rstrip('/')
        if key:
            os.environ[f'{up}_PROVIDER_KEY'] = key
    elif key:
        os.environ[PROVIDERS[provider]['key']] = key
    if model:
        os.environ[f'{up}_MODEL'] = model


def mneme_serve(writable):
    from mneme import mcp
    safe = {'mneme.status', 'mneme.doctor', 'mneme.to_crucible', 'mneme.origin_recheck'}
    # Preserve Mneme's duplicate-key handling but avoid global snapshot cleanup
    # on a profile that cannot create or delete snapshots.
    if writable:
        mcp.snapshot_dir.startup_sweep()
    for line in sys.stdin:
        try:
            req = json.loads(line, object_pairs_hook=mcp._unique_json_object)
            if not isinstance(req, dict):
                raise ValueError('request must be an object')
            params = req.get('params') or {}
            if not isinstance(params, dict):
                raise ValueError('params must be an object')
            if req.get('method') == 'tools/call' and not writable and params.get('name') not in safe:
                response = mcp._err(req.get('id'), -32602, 'tool unavailable in bound export profile; explicit memory-write launch required')
            else:
                response = mcp.handle_request(req)
            if response and req.get('method') == 'tools/list' and not writable:
                response['result']['tools'] = [t for t in response['result']['tools'] if t['name'] in safe]
        except (ValueError, TypeError, AttributeError) as exc:
            response = mcp._err(None, -32600, str(exc))
        if response is not None:
            print(json.dumps(response), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    if TOOL == 'mneme':
        parser.add_argument('--allow-memory-write', action='store_true')
    if TOOL == 'relay':
        parser.add_argument('--allow-write', action='store_true')
        parser.add_argument('--allow-exec', action='store_true')
        parser.add_argument('--write', choices=('true', 'false'), default='false')
        parser.add_argument('--exec', choices=('true', 'false'), default='false')
        parser.add_argument('--api-provider', default='')
        parser.add_argument('--api-base-url', default='')
        parser.add_argument('--api-model', default='')
        parser.add_argument('--no-cli-tiers', action='store_true')
    args = parser.parse_args(argv)
    try:
        if TOOL == 'mneme':
            os.environ['MNEME_STATE'] = explicit_path(os.environ.get('MNEME_STATE'))
            return mneme_serve(args.allow_memory_write)
        if TOOL == 'relay':
            root = explicit_path(os.environ.get('RELAY_MCP_ROOT'), directory=True)
            hosted_environment(args.api_provider, args.api_base_url, args.api_model)
            from relay.local_mcp import serve
            from relay.mcp_grants import StartGrants
            return serve(grants=StartGrants(allow_write=args.allow_write or args.write == 'true',
                                           allow_exec=args.allow_exec or args.exec == 'true', root=root),
                         cli_tiers=not args.no_cli_tiers)
        from plexus.mcp import serve
        return serve()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

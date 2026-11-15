"""Standard-library editor adapters with bounded, content-free failure receipts.

MCP auto uses the calling model, never an implicit separately billed backend.
LOCAL_ONLY permits only loopback Ollama and deterministic work. Ollama only
uses installed models; no adapter pulls or downloads a model.
"""
import ipaddress
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Optional

from . import claude_cli

BACKENDS = ('auto', 'host', 'sampling', 'anthropic', 'claude-cli', 'openai', 'ollama', 'none')
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
# Verified 2026-09-28: https://platform.claude.com/docs/en/models/overview
ANTHROPIC_MODEL = 'claude-sonnet-5'
OPENAI_BASE_URL = 'https://api.openai.com/v1'
OLLAMA_URL = 'http://127.0.0.1:11434'
OLLAMA_PREFERENCE = ('qwen3:8b', 'qwen2.5:7b', 'llama3.2:3b', 'gemma3:4b')
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


@dataclass
class BackendInfo:
    backend: str
    model: Optional[str] = None
    attempts: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class BackendUnavailable(RuntimeError):
    """Only static, content-free messages may be used with this exception."""


def local_only():
    return os.environ.get('ARTICULATE_LOCAL_ONLY', '').strip().lower() not in ('', '0', 'false', 'no', 'off')


def _loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _endpoint(url, *, require_local=False):
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
        port = parts.port
        if (parts.scheme not in ('http', 'https') or not host or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment
                or any(c.isspace() for c in url)):
            raise ValueError
        loopback = _loopback(host)
        if require_local and not loopback:
            raise BackendUnavailable('LOCAL_ONLY requires a loopback Ollama URL')
        if parts.scheme == 'http' and not loopback:
            raise BackendUnavailable('remote endpoints require HTTPS')
        # Pin localhost to the literal loopback address, avoiding DNS overrides.
        if host == 'localhost':
            authority = '127.0.0.1' + (':' + str(port) if port else '')
            url = urllib.parse.urlunsplit((parts.scheme, authority, parts.path, '', ''))
        return url.rstrip('/'), loopback
    except (ValueError, TypeError):
        raise BackendUnavailable('invalid backend URL') from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(url, payload=None, headers=None, timeout=600):
    url, loopback = _endpoint(url)
    handlers = [_NoRedirect()]
    # Never send local requests through a proxy, regardless of NO_PROXY.
    if loopback:
        handlers.append(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.build_opener(*handlers).open(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise BackendUnavailable('backend response exceeds size limit')
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise BackendUnavailable('HTTP %d' % code) from None
    except (OSError, urllib.error.URLError):
        raise BackendUnavailable('connection failed or timed out') from None
    except (ValueError, UnicodeError):
        raise BackendUnavailable('invalid backend response') from None


def _model(value):
    # Model identifiers are metadata, not an arbitrary response/error channel.
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/+@-]{0,159}', value):
        return value
    return None


def _output(value):
    if not isinstance(value, str) or not value.strip():
        raise BackendUnavailable('backend returned no text')
    return value.strip()


def _anthropic(instructions, text, timeout):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        raise BackendUnavailable('ANTHROPIC_API_KEY is not configured')
    model = os.environ.get('ARTICULATE_MODEL') or ANTHROPIC_MODEL
    result = _request(ANTHROPIC_URL, {'model':model, 'max_tokens':8192, 'system':instructions,
        'messages':[{'role':'user','content':text}]},
        {'x-api-key':key, 'anthropic-version':'2023-06-01'}, timeout)
    content = result.get('content', [])
    output = ''.join(item.get('text', '') for item in content if isinstance(item, dict) and item.get('type') == 'text')
    return _output(output), _model(result.get('model')) or _model(model)


def _openai(instructions, text, timeout):
    base = os.environ.get('ARTICULATE_OPENAI_BASE_URL') or OPENAI_BASE_URL
    base, _ = _endpoint(base)
    key = os.environ.get('ARTICULATE_OPENAI_API_KEY')
    if base == OPENAI_BASE_URL:
        key = key or os.environ.get('OPENAI_API_KEY')
        if not key:
            raise BackendUnavailable('OpenAI API key is not configured')
    model = os.environ.get('ARTICULATE_MODEL')
    if not model:
        raise BackendUnavailable('set ARTICULATE_MODEL for the OpenAI-compatible endpoint')
    headers = {'Authorization':'Bearer ' + key} if key else {}
    result = _request(base + '/chat/completions', {'model':model, 'stream':False,
        'messages':[{'role':'system','content':instructions},{'role':'user','content':text}]}, headers, timeout)
    try:
        output = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        raise BackendUnavailable('invalid backend response') from None
    return _output(output), _model(result.get('model')) or _model(model)


def _ollama(instructions, text, timeout):
    base, _ = _endpoint(os.environ.get('ARTICULATE_OLLAMA_URL') or OLLAMA_URL, require_local=local_only())
    tags = _request(base + '/api/tags', timeout=min(timeout, 5))
    installed = [item['name'] for item in tags.get('models', [])
                 if isinstance(item, dict) and _model(item.get('name'))]
    requested = os.environ.get('ARTICULATE_LOCAL_MODEL')
    if requested:
        model = next((name for name in installed if name == requested or name == requested + ':latest'), None)
        if model is None:
            raise BackendUnavailable('configured Ollama model is not installed; no download attempted')
    else:
        model = next((name for name in OLLAMA_PREFERENCE if name in installed), None)
        model = model or (installed[0] if installed else None)
    if model is None:
        raise BackendUnavailable('no installed Ollama models; no download attempted')
    result = _request(base + '/api/chat', {'model':model, 'stream':False, 'think':False,
        'messages':[{'role':'system','content':instructions},{'role':'user','content':text}]}, timeout=timeout)
    return _output(result.get('message', {}).get('content')), _model(result.get('model')) or model


def _claude(instructions, text, timeout):
    try:
        status = claude_cli.auth_status(timeout=min(timeout, 15))
    except claude_cli.ClaudeUnavailable:
        raise BackendUnavailable('claude CLI not found, cannot start, or auth status unavailable') from None
    if status.get('loggedIn') is not True:
        raise BackendUnavailable('claude CLI not logged in; run `claude login`')
    result = claude_cli.run(instructions, text, timeout)
    if result.returncode:
        error = ((result.stdout or '') + ' ' + (result.stderr or '')).lower()
        if 'credit balance' in error:
            if 'subscriptionType' in status and status['subscriptionType'] is None:
                raise BackendUnavailable('CLI account has no subscription and no API credit; use `claude login` '
                    'with a subscription account, ANTHROPIC_API_KEY, or a local backend')
            raise BackendUnavailable('CLI API credit unavailable; set ANTHROPIC_API_KEY or use a local backend')
        if 'rate limit' in error:
            raise BackendUnavailable('claude CLI rate limited')
        if any(word in error for word in ('not authenticated', 'invalid api key', 'unauthorized')):
            raise BackendUnavailable('claude CLI authentication failed; run `claude login`')
        raise BackendUnavailable('claude CLI call failed')
    # CLI plain text does not report its resolved model. Do not invent one.
    return _output(result.stdout), None


def _sampling(instructions, text, timeout, sampling, advertised, context):
    if context != 'mcp' or not advertised or sampling is None:
        raise BackendUnavailable('MCP sampling is not available or advertised')
    try:
        result = sampling(instructions, text, timeout)
        if isinstance(result, tuple) and len(result) == 2:
            return _output(result[0]), _model(result[1])
        content = result['content']
        if isinstance(content, list):
            value = ''.join(item['text'] for item in content if item.get('type') == 'text')
        else:
            value = content['text'] if content.get('type') == 'text' else ''
        return _output(value), _model(result.get('model'))
    except Exception:
        raise BackendUnavailable('MCP sampling failed or returned no text') from None


def complete(instructions, text, timeout=600, *, backend=None, context='cli', sampling=None,
             sampling_advertised=False):
    """Return model text and provenance, or empty text for host/none work.

    Sampling callbacks take (instructions, text, timeout) and return either
    (text, model) or an MCP createMessage result. An environment backend is a
    CLI preference; only an explicit argument authorizes MCP billed routes.
    """
    choice = backend if backend is not None else ('auto' if context == 'mcp' else os.environ.get('ARTICULATE_BACKEND', 'auto'))
    if choice not in BACKENDS:
        raise ValueError('unknown editor backend')
    attempts = []
    terminal = 'host' if context == 'mcp' and not local_only() else 'none'
    if choice == 'none':
        return '', BackendInfo('none')
    if local_only():
        if choice not in ('auto', 'ollama'):
            attempts.append({'backend':choice, 'reason':'refused by ARTICULATE_LOCAL_ONLY'})
        order = ['ollama', 'none']
    elif choice == 'host':
        order = ['host']
    elif context == 'mcp' and choice == 'auto':
        order = ['sampling', 'host'] if sampling_advertised else ['host']
    elif choice == 'sampling':
        order = ['sampling', terminal]
    else:
        chain = ['anthropic', 'claude-cli', 'openai', 'ollama']
        order = chain if choice == 'auto' else [choice] + [item for item in chain if item != choice]
        order.append(terminal)
    adapters = {'anthropic':_anthropic, 'claude-cli':_claude, 'openai':_openai, 'ollama':_ollama}
    for name in order:
        if name in ('none', 'host'):
            return '', BackendInfo(name, attempts=attempts)
        try:
            if name == 'sampling':
                output, model = _sampling(instructions, text, timeout, sampling, sampling_advertised, context)
            else:
                output, model = adapters[name](instructions, text, timeout)
            return output, BackendInfo(name, model, attempts)
        except BackendUnavailable as exc:
            reason = str(exc)
        except subprocess.TimeoutExpired:
            reason = 'backend timed out'
        except Exception:
            # Subprocess, malformed response, and third-party errors may contain
            # credentials or document content. Never copy their messages.
            reason = 'backend unavailable or returned an invalid response'
        attempts.append({'backend':name, 'reason':reason})

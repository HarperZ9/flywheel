"""Explicit launcher grants reach the existing gated tool executor."""
import importlib.util
import io
from pathlib import Path
import sys

import relay.local_mcp as m


def test_explicit_write_launch_reaches_bound_executor(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[1]/'client-plugin/server/serve.py'
    spec=importlib.util.spec_from_file_location('relay_client_entry',path)
    entry=importlib.util.module_from_spec(spec); spec.loader.exec_module(entry)
    monkeypatch.setenv('RELAY_MCP_ROOT',str(tmp_path))
    monkeypatch.setenv('RELAY_ALLOW_EXEC','1')
    monkeypatch.setattr(sys,'stdin',io.StringIO(''))
    monkeypatch.setattr(sys,'stdout',io.StringIO())
    assert entry.main(['--allow-write']) == 0
    assert m._GRANTS.allow_write and not m._GRANTS.allow_exec
    binding=m._request_binding({'goal':'synthetic','root':str(tmp_path),'allow_write':True})
    ex=m._executor({},binding)
    result=ex.execute('write_file',{'path':'synthetic.txt','content':'synthetic content'})
    assert result.ok
    assert (tmp_path/'synthetic.txt').read_text() == 'synthetic content'
    assert not ex.execute('run',{'cmd':'echo forbidden'}).ok

"""Reviewed source closure for the two-tool, two-resource MCP companion."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import stat

from scripts.native_mcp_payload import safe_name

REVIEW = Path(__file__).with_name('source_tool_closure.json')
TEMPLATE = 'plugins/flywheel-tools'
TEMPLATE_FILES = ('README.md', 'skills/flywheel-tools/SKILL.md', 'server/serve.py')


def read_public(repo, relative):
    safe_name(relative)
    root = Path(repo).resolve(strict=True)
    target = root / relative
    for path in (target, *target.parents):
        info = path.lstat()
        if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('source payload contains a linked path')
        if path == root:
            break
    if not stat.S_ISREG(target.stat().st_mode):
        raise ValueError('source payload must contain regular files')
    data = target.read_bytes().decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
    if len(data) >= 256 * 1024 or b'\0' in data:
        raise ValueError('source payload exceeds readable-text limits')
    data.decode('utf-8')
    return data


def reviewed_payload(repo, snapshots=None):
    """LF-normalized pins cover complete reviewed modules, including lazy bodies.

    The unchanged gateway import closure contains unused lazy functionality.
    It is not recursively bundled. Any change to a reviewed module requires a
    deliberate closure review and pin update before this builder can proceed.
    """
    def read(name):
        return read_public(repo, name) if snapshots is None else snapshots[name]
    review = json.loads(REVIEW.read_text(encoding='utf-8') if snapshots is None
                        else snapshots['scripts/source_tool_closure.json'].decode('utf-8'))
    if len(review) != 80 or len({name.casefold() for name in review}) != len(review):
        raise ValueError('invalid reviewed source closure')
    files = {}
    for name, expected in sorted(review.items()):
        data = read(name)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('reviewed source closure changed: ' + name)
        files['server/' + name] = data
    files['server/pyproject.toml'] = read('pyproject.toml')
    files['LICENSE'] = read('LICENSE')
    for relative in TEMPLATE_FILES:
        files[relative] = read(TEMPLATE + '/' + relative)
    return files


def verify_payload(files):
    if len(files) > 512 or sum(map(len, files.values())) >= 50 * 1024 * 1024:
        raise ValueError('source plugin exceeds directory limits')
    folded = set()
    for name, data in files.items():
        safe_name(name)
        if name.casefold() in folded or len(data) >= 256 * 1024 or b'\0' in data:
            raise ValueError('invalid source plugin member')
        folded.add(name.casefold())
        data.decode('utf-8')

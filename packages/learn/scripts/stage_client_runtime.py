"""Stage the one approved Node runtime for client builds; no model downloads."""
import argparse
import hashlib
from pathlib import Path
import urllib.request
import zipfile
import io

from build_client_plugin import NODE_HASHES

URL = 'https://nodejs.org/dist/v24.21.0/node-v24.21.0-win-x64.zip'
SHA256 = '158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541'


def stage(out):
    if out.exists():
        raise FileExistsError('runtime destination must not exist')
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('upstream runtime archive hash mismatch')
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name, digest in NODE_HASHES.items():
            content = archive.read('node-v24.21.0-win-x64/' + name)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError('runtime member hash mismatch')
            files[name] = content
    out.mkdir(parents=True)
    for name, content in files.items():
        (out / name).write_bytes(content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    stage(parser.parse_args().out)

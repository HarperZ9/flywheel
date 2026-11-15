"""Release checksum files pass sha256sum -c on Linux, whichever OS wrote them.

The Windows release job wrote the client .sha256 file with Path.write_text,
which emits CRLF there. GNU sha256sum 8.32 and Perl shasum then fail to open the
listed files. The checksums workflow runs these checks on Windows and Linux.
"""
import hashlib
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('client_builder', ROOT / 'scripts/build_client_plugin.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

LINE = re.compile(rb'[0-9a-f]{64}  [^\r\n/]+\n')


class ReleaseChecksums(unittest.TestCase):
    def test_checksum_file_is_lf_only_and_names_each_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            alpha, beta = Path(tmp) / 'alpha.zip', Path(tmp) / 'beta.mcpb'
            alpha.write_bytes(b'alpha\n')
            beta.write_bytes(b'beta\r\n')
            target = Path(tmp) / 'client.sha256'
            builder.write_sums(target, [alpha, beta])
            data = target.read_bytes()
            self.assertNotIn(b'\r', data)
            lines = data.splitlines(keepends=True)
            self.assertTrue(all(LINE.fullmatch(line) for line in lines), data)
            self.assertEqual(lines, [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'.encode()
                                     for p in (alpha, beta)])

    def test_no_script_writes_a_checksum_file_as_text(self):
        offenders = [f'{path.name}:{number}'
                     for path in sorted((ROOT / 'scripts').glob('*.py')) if path.name != Path(__file__).name
                     for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
                     if 'write_text(' in line and ('SUMS' in line or '.sha256' in line)]
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()

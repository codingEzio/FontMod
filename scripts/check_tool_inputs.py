"""Check separately supplied font inputs before invoking the build environment."""
import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
catalog = json.loads((root / 'sources/catalog.json').read_text())['sources']
emoji = json.loads((root / 'sources/emoji3d.json').read_text())
records = json.loads((root / 'sources/geist-mixed/sources.json').read_text())
pins = [(r['path'], r['sha256']) for r in [*catalog.values(), emoji]]
pins.extend(('sources/geist-mixed/' + r['file'], r['sha256']) for r in records)
for name, expected in pins:
    p = Path(os.environ.get('FONTMOD_INPUT_ROOT', str(root))).expanduser() / name if name.endswith(('.ttf', '.woff2')) else root / name
    if not p.is_file():
        print('Missing input: ' + name, file=sys.stderr)
        sys.exit(1)
    if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
        print('Input SHA-256 mismatch: ' + name, file=sys.stderr)
        sys.exit(1)
print('Pinned source inputs verified')

"""Prepare the pinned Noto 3D input without replacing existing files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from font_mixed_support import slim_emoji

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='pinned upstream Noto-3D-128.ttf')
    parser.add_argument('output', type=Path, help='new Noto3D-64.ttf input path')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'sources/emoji3d.json').read_text(encoding='utf-8'))
    if not args.source.is_file():
        parser.error('upstream source must be an existing file')
    if args.output.exists() or args.output.is_symlink():
        parser.error('output already exists; choose a new path')
    if not args.output.parent.is_dir():
        parser.error('output parent directory does not exist')
    if sha256(args.source) != manifest['upstreamSha256']:
        parser.error('upstream source SHA-256 does not match sources/emoji3d.json')
    with tempfile.TemporaryDirectory(prefix='.fontmod-emoji-', dir=args.output.parent) as work:
        candidate = Path(work) / 'Noto3D-64.ttf'
        slim_emoji(args.source, 55, candidate)
        if sha256(candidate) != manifest['sha256']:
            parser.error('prepared input SHA-256 does not match sources/emoji3d.json')
        # Linking in the same directory is atomic and refuses an existing output.
        os.link(candidate, args.output)
    print('Prepared Noto3D-64.ttf; both pinned SHA-256 values verified')


if __name__ == '__main__':
    main()

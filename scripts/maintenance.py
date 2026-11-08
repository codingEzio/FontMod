"""Local source candidate checks; no network, installation or Git mutation."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'personal-path': re.compile(r'(?:/Users/|/home/|[A-Z]:\\Users\\)[A-Za-z0-9_.-]+[/\\]'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'provider-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect(index=False):
    def read(name):
        p = ROOT / name
        if index:
            return subprocess.check_output(['git', '-C', str(ROOT), 'show', ':' + name])
        if any((ROOT / Path(*p.relative_to(ROOT).parts[:i])).is_symlink() for i in range(1, len(p.relative_to(ROOT).parts) + 1)) or not p.is_file() or not p.resolve().is_relative_to(ROOT):
            raise ValueError('Missing or unsafe source path: ' + name)
        return p.read_bytes()
    policy = json.loads(read('release-files.json'))
    names = policy['files']
    if names != sorted(set(names)) or 'release-files.json' not in names:
        raise ValueError('Allowlist must be sorted, unique and include itself')
    result = {}
    modes = {}
    for name in names:
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or str(p) != name or p.parts[0] in {'.git', 'Local', 'Evidence', 'Final', '.cache', '.venv'}:
            raise ValueError('Unsafe allowlist path')
        data = read(name)
        if index:
            entry = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--stage', '--', name], text=True)
            if not entry.startswith(('100644 ', '100755 ')):
                raise ValueError('Unsupported index mode: ' + name)
            modes[name] = int(entry.split()[0], 8) & 0o777
        else:
            modes[name] = stat.S_IMODE((ROOT / name).stat().st_mode)
            if modes[name] not in {0o644, 0o755}:
                raise ValueError('Unsupported source mode: ' + name)
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            if p.suffix.lower() not in {'.ttf', '.woff2'}:
                reviewed = policy.get('reviewedImages', {}).get(name, {})
                record_name = reviewed.get('sourceRecord', '')
                if (p.suffix.lower() != '.png' or not data.startswith(b'\x89PNG\r\n\x1a\n')
                        or sha(data) != reviewed.get('sha256') or record_name not in names):
                    raise ValueError('Unexpected or changed binary source: ' + name)
                record = json.loads(read(record_name))
                if record.get('kind') != 'font-specimen' or record.get('image', {}).get('sha256') != sha(data):
                    raise ValueError('Font specimen provenance differs: ' + name)
        else:
            for category, pattern in PATTERNS.items():
                if pattern.search(text):
                    raise ValueError(category + ': ' + name)
        if p.suffix == '.py':
            compile(data, name, 'exec')
        result[name] = data
    # Verify original font and license pins without importing font tools.
    catalog = json.loads(result['sources/catalog.json'])['sources'].values()
    emoji = json.loads(result['sources/emoji3d.json'])
    pins = [(r['path'], r['sha256']) for r in [*catalog, emoji]]
    pins += [(r['license']['path'], r['license']['sha256']) for r in [*catalog, emoji]]
    pins += [('sources/geist-mixed/' + r['file'], r['sha256']) for r in json.loads(result['sources/geist-mixed/sources.json'])]
    for name, expected in pins:
        if name in result:
            data = result[name]
        elif PurePosixPath(name).suffix.lower() in {'.ttf', '.woff2'}:
            # Build inputs are intentionally absent from this tool-only export.
            # If supplied, validate them without adding them to the export.
            candidate = Path(os.environ.get('FONTMOD_INPUT_ROOT', str(ROOT))).expanduser() / name
            if not candidate.exists():
                continue
            data = candidate.read_bytes()
        else:
            raise ValueError('Pinned license missing: ' + name)
        if sha(data) != expected:
            raise ValueError('Pinned source or license differs: ' + name)
    for name in policy['requiredNotices']:
        if not result.get(name):
            raise ValueError('Required notice missing: ' + name)
    return result, modes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['source-check', 'source-export', 'release-check', 'dependency-check'])
    parser.add_argument('--index', action='store_true', help='check staged bytes and modes')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--publication', action='store_true', help='release-check: additionally reject unresolved rights decisions')
    parser.add_argument('--departure-build', type=Path, help='dependency-check: compare rebuilt Departure font hashes')
    args = parser.parse_args()
    if args.publication and args.command != 'release-check':
        parser.error('--publication belongs to release-check')
    if args.command in {'release-check', 'dependency-check'}:
        import release
        if args.index:
            parser.error('--index belongs to source-check/source-export')
        if args.command == 'release-check':
            if args.output is None:
                parser.error('release-check requires --output RELEASE_DIRECTORY')
            result = release.verify(args.output)
            if args.publication:
                release.check_rights_hold(args.output)
                result['rightsBlockers'] = 'none-recorded'
            print(json.dumps(result))
        else:
            if args.output is not None:
                parser.error('dependency-check reads this source kit dependencies/')
            print(json.dumps(release.check_dependencies(ROOT, args.departure_build)))
        return
    if args.departure_build is not None:
        parser.error('--departure-build belongs to dependency-check')
    if args.command == 'source-export' and args.output is None:
        parser.error('source-export requires a new --output directory')
    if args.command == 'source-check' and args.output is not None:
        parser.error('--output belongs to source-export')
    files, modes = collect(args.index)
    receipt = {'schemaVersion': 1, 'scope': 'local-source-candidate', 'licenseStatus': 'MIT-tooling; font-component-licenses-retained',
               'historyIncluded': False, 'files': [{'path': p, 'sha256': sha(b), 'bytes': len(b), 'mode': oct(modes[p])} for p, b in files.items()]}
    if args.output:
        out = args.output.absolute()
        if out.exists() or out.is_symlink():
            raise ValueError('Output already exists')
        out.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='delete_after_use_source_', dir=out.parent))
        try:
            for name, data in files.items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                if target.read_bytes() != data:
                    raise ValueError('Candidate readback mismatch: ' + name)
                target.chmod(modes[name])
                if stat.S_IMODE(target.stat().st_mode) != modes[name]:
                    raise ValueError('Candidate mode readback mismatch: ' + name)
            receipt_path = stage / 'source-receipt.json'
            receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
            if json.loads(receipt_path.read_text()) != receipt:
                raise ValueError('Candidate receipt readback mismatch')
            actual = sorted(str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file())
            if actual != sorted([*files, 'source-receipt.json']):
                raise ValueError('Unexpected candidate file')
            stage.rename(out)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    print(json.dumps({'result': 'pass', 'files': len(files), 'index': args.index,
                      'licenseStatus': receipt['licenseStatus'], 'historyReviewed': False}))


if __name__ == '__main__':
    main()

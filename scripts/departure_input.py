"""Validate the explicitly supplied Departure build and retain its notices."""
import json
from pathlib import Path
import shutil
from final_fonts import ROOT, sha, write

NAMES = ['DeparturePixelZh-Regular', 'DeparturePixelZhCompact-Regular']


def resolve(directory=None):
    source = Path(directory).resolve() if directory is not None else ROOT / 'departure-build'
    report = json.loads((source / 'provenance.json').read_text())
    for name in NAMES:
        filename = name + '.ttf'
        expected = next((v['files'].get(filename) for v in report['variants'] if filename in v['files']), None)
        if expected is None or sha(source / filename) != expected:
            raise ValueError('Departure producer font mismatch: ' + filename)
    for name in ['NOTICE.md', 'OFL.txt']:
        if not (source / name).is_file():
            raise ValueError('Departure required notice missing: ' + name)
    notices = [source / 'NOTICE.md', source / 'OFL.txt', *sorted((source / 'Licenses').rglob('*'))]
    if not (source / 'Licenses').is_dir() or len(notices) <= 2:
        raise ValueError('Departure requires complete Licenses directory')
    for path in notices:
        if path.is_symlink():
            raise ValueError('Departure notice must not be a symlink')
        if path.is_file():
            path.read_bytes()
    return source, report


def retain(source, report):
    """Record this project's derived outputs separately from producer hashes."""
    dest = ROOT / 'Final/departure-package'
    dest.mkdir(parents=True, exist_ok=True)
    for name in ['NOTICE.md', 'OFL.txt']:
        shutil.copyfile(source / name, dest / name)
        if sha(source / name) != sha(dest / name):
            raise ValueError('Departure notice readback mismatch')
    # Merge existing notices without deleting retained originals.
    shutil.copytree(source / 'Licenses', dest / 'Licenses', dirs_exist_ok=True)
    for path in (source / 'Licenses').rglob('*'):
        if path.is_file() and sha(path) != sha(dest / 'Licenses' / path.relative_to(source / 'Licenses')):
            raise ValueError('Departure license readback mismatch')
    write(dest / 'provenance.json', {'schemaVersion': 1, 'producer': report,
          'modification': 'Apply final_fonts.json symbolAliases; preserve geometry and family identity.',
          'files': {name + ext: sha(ROOT / 'Final' / (name + ext)) for name in NAMES for ext in ['.ttf', '.woff2']}})

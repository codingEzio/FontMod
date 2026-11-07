"""Exercise the release-check rights hold with synthetic local candidates."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def run(path, *extra):
    return subprocess.run([str(ROOT / 'fontmod'), 'release-check', '--output', str(path), *extra],
                          text=True, capture_output=True)

def fixture(path, decisions, mismatch=False):
    path.mkdir()
    rights = {'status': 'test', 'blockingDecisions': decisions}
    content = (json.dumps(rights) + '\n').encode()
    (path / 'RELEASE-RIGHTS.json').write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    manifest = {'packages': [], 'entryFiles': {'RELEASE-RIGHTS.json': digest},
                'recipeVersion': 'test', 'sourceRevision': 'synthetic',
                'rightsReview': {'sha256': digest, 'status': 'test',
                                 'blockingDecisions': [] if mismatch else [x['id'] for x in decisions]}}
    (path / 'release-manifest.json').write_text(json.dumps(manifest))
    (path / 'SHA256SUMS').write_text('')

with tempfile.TemporaryDirectory(prefix='fontmod-rights-test-') as temporary:
    root = Path(temporary)
    held = root / 'held'; fixture(held, [{'id': 'font-logos-rights-discrepancy'}])
    plain = run(held); blocked = run(held, '--publication')
    assert plain.returncode == 0, plain.stderr
    assert blocked.returncode != 0 and 'font-logos-rights-discrepancy' in blocked.stderr, blocked.stderr
    mdi = root / 'mdi-brand-logos'; fixture(mdi, [{'id': 'material-design-brand-logos-rights-classification'}])
    mdi_plain = run(mdi); mdi_blocked = run(mdi, '--publication')
    assert mdi_plain.returncode == 0, mdi_plain.stderr
    assert mdi_blocked.returncode != 0 and 'material-design-brand-logos-rights-classification' in mdi_blocked.stderr, mdi_blocked.stderr
    clear = root / 'clear'; fixture(clear, [])
    passed = run(clear, '--publication'); assert passed.returncode == 0, passed.stderr
    mismatch = root / 'mismatch'; fixture(mismatch, [{'id': 'held'}], mismatch=True)
    failed = run(mismatch, '--publication'); assert failed.returncode != 0 and 'differs' in failed.stderr, failed.stderr
    bad = run(held, '--publication', '--index'); assert bad.returncode != 0
    print('pass: integrity review, Font Logos hold, MDI Brand/Logos hold, no recorded hold, mismatch, invalid flags')

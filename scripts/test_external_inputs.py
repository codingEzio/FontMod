"""Exercise external input and output boundaries with synthetic files."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(env, *args):
    return subprocess.run([str(ROOT / 'fontmod'), *map(str, args)], env=env,
                          text=True, capture_output=True)


with tempfile.TemporaryDirectory(prefix='fontmod-input-test-') as temp:
    base = Path(temp)
    inputs = base / 'input'
    (inputs / 'sources').mkdir(parents=True)
    env = {**os.environ, 'FONTMOD_INPUT_ROOT': str(inputs), 'PYTHONDONTWRITEBYTECODE': '1'}
    missing = run(env, 'build')
    assert missing.returncode and 'Missing input: sources/Doto-Variable.ttf' in missing.stderr
    (inputs / 'sources/Doto-Variable.ttf').write_bytes(b'incorrect')
    mismatch = run(env, 'build')
    assert mismatch.returncode and 'Input SHA-256 mismatch' in mismatch.stderr
    source = run(env, 'source-check')
    assert source.returncode and 'Pinned source or license differs' in source.stderr
    profile = run(env, 'build', '--profile', 'rysamix', '--output', base / 'result')
    assert profile.returncode and 'recipe.json' in profile.stderr
    local = run(env, 'build', '--profile', 'rysamix', '--output', ROOT / 'Local/test')
    assert local.returncode and 'outside the source checkout' in local.stderr
    recipe = base / 'recipe.json'
    recipe.write_text(json.dumps({'inputSha256': {'bad.ttf': '0' * 64}}))
    (inputs / 'bad.ttf').write_bytes(b'incorrect')
    glyph = run(env, 'glyphgrove', '--inputs', inputs, '--recipe', recipe, '--output', base / 'glyph')
    assert glyph.returncode and 'Source digest mismatch' in glyph.stderr and not (base / 'glyph').exists()
    print('pass: missing and mismatched inputs, profile dispatch, external outputs, Glyphgrove hash guard')

"""Check local input-root precedence and failures with synthetic directories."""
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from input_root import resolve_input_root

with tempfile.TemporaryDirectory(prefix='fontmod-config-test-') as temp:
    base = Path(temp).resolve()
    root, configured, override = (base / n for n in ('checkout', 'configured', 'override'))
    for path in (root, configured, override):
        path.mkdir()
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_input_root(root) == root
        local = root / 'Local'
        local.mkdir()
        setting = local / 'input-root'
        setting.write_text(str(configured) + '\n')
        assert resolve_input_root(root) == configured
        with patch.dict(os.environ, {'FONTMOD_INPUT_ROOT': str(override)}):
            assert resolve_input_root(root) == override
        for value in ('', 'relative/path', str(base / 'missing'), 'one\ntwo\n'):
            setting.write_text(value)
            try:
                resolve_input_root(root)
            except ValueError as error:
                assert 'Local/input-root' in str(error)
            else:
                raise AssertionError('Invalid setting accepted')
        setting.write_bytes(b'\xff')
        try:
            resolve_input_root(root)
        except ValueError as error:
            assert 'Local/input-root must be UTF-8' in str(error)
        else:
            raise AssertionError('Invalid UTF-8 accepted')
        with patch.dict(os.environ, {'FONTMOD_INPUT_ROOT': ''}):
            try:
                resolve_input_root(root)
            except ValueError as error:
                assert 'FONTMOD_INPUT_ROOT' in str(error)
            else:
                raise AssertionError('Invalid environment override accepted')
print('pass: missing setting, local input root, environment precedence and invalid values')

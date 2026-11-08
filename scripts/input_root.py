"""Resolve local font inputs without evaluating configuration as code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_input_root(root=ROOT):
    root = Path(root).resolve()
    config = root / 'Local/input-root'
    if 'FONTMOD_INPUT_ROOT' in os.environ:
        value = os.environ['FONTMOD_INPUT_ROOT']
        source = 'FONTMOD_INPUT_ROOT'
    elif config.exists() or config.is_symlink():
        try:
            value = config.read_text(encoding='utf-8')
        except UnicodeError as error:
            raise ValueError('Local/input-root must be UTF-8 text') from error
        except OSError as error:
            raise ValueError('Local/input-root cannot be read') from error
        source = 'Local/input-root'
    else:
        return root
    lines = value.splitlines()
    if len(lines) != 1 or not lines[0].strip() or '\x00' in value:
        raise ValueError(source + ' must contain one non-empty directory path')
    path = Path(lines[0].strip()).expanduser()
    if not path.is_absolute():
        raise ValueError(source + ' must be an absolute directory path')
    if not path.is_dir():
        raise ValueError(source + ' must name an existing directory')
    return path.resolve()

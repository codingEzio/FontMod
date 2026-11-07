"""Audit and export the staged source of the two DeparturePixelZh repositories."""

import hashlib
import json
import os
import subprocess
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from .audit import require_clean


def _git(root, *arguments):
    try:
        return subprocess.check_output(["git", "-C", str(root), *arguments], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        raise ValueError("Git source snapshot could not be read") from error


def _relative(value):
    path = PurePosixPath(value)
    if (
        not isinstance(value, str)
        or not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"..", ".git"} for part in path.parts)
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Unsafe source path")
    return path


def audit_index(root, destination=None):
    """Read exact index blobs; never follow checkout links or export private caches."""
    root = Path(root).resolve()
    if Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve() != root:
        raise ValueError("Audit root must be a repository root")
    entries = {}
    for entry in _git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, blob, stage = metadata.decode("ascii").split()
        name = os.fsdecode(raw_path)
        _relative(name)
        if stage != "0" or mode not in {"100644", "100755"}:
            raise ValueError("Index has an unresolved path, symbolic link, or submodule")
        entries[name] = (mode, blob)
    if not entries:
        raise ValueError("Index is empty")
    # A detached temporary snapshot prevents both unstaged masking and link traversal.
    with TemporaryDirectory(prefix="departure-source-") as temporary:
        snapshot = Path(temporary)
        hashes = {}
        for name, (mode, blob) in sorted(entries.items()):
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            data = _git(root, "cat-file", "blob", blob)
            target.write_bytes(data)
            target.chmod(0o755 if mode == "100755" else 0o644)
            hashes[name] = hashlib.sha256(data).hexdigest()
        report = require_clean(snapshot)
        report["scope"] = "index"
        if destination is None:
            return report
        manifest = json.loads((snapshot / "public-source.json").read_text())
        if set(manifest) != {"schema_version", "files"} or manifest["schema_version"] != 1:
            raise ValueError("Invalid public-source.json schema")
        names = manifest["files"]
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise ValueError("Public source files must be a list of paths")
        if len(names) != len(set(names)) or set(names) != set(entries):
            raise ValueError("Public source allowlist must exactly match the audited index")
        if "SOURCE-RECEIPT.json" in entries:
            raise ValueError("SOURCE-RECEIPT.json is reserved for export receipts")
        destination = Path(destination).absolute()
        if destination.exists() or destination.is_symlink():
            raise ValueError("Source export destination already exists")
        if not destination.parent.is_dir():
            raise ValueError("Source export parent must already exist")
        # Stage beside the destination, then rename only after full byte/mode readback.
        with TemporaryDirectory(prefix=".departure-export-", dir=destination.parent) as staging:
            staging = Path(staging)
            for name, (mode, _) in entries.items():
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((snapshot / name).read_bytes())
                target.chmod(0o755 if mode == "100755" else 0o644)
                if hashlib.sha256(target.read_bytes()).hexdigest() != hashes[
                    name
                ] or target.stat().st_mode & 0o777 != (0o755 if mode == "100755" else 0o644):
                    raise ValueError("Source export readback failed")
            receipt = {
                "schema_version": 1,
                "scope": "index",
                "files": hashes,
                "modes": {name: entry[0] for name, entry in entries.items()},
            }
            (staging / "SOURCE-RECEIPT.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n"
            )
            if json.loads((staging / "SOURCE-RECEIPT.json").read_text()) != receipt:
                raise ValueError("Source receipt readback failed")
            staging.rename(destination)
        report["exported_files"] = len(hashes)
        report["receipt"] = "SOURCE-RECEIPT.json"
        return report

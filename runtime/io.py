import hashlib
import json
import os
import tempfile
from pathlib import Path, PureWindowsPath

import yaml

from runtime.errors import BoundaryError, ValidationError
from runtime.env_config import load_dotenv, resolve_environment


DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def filesystem_path(path):
    """Resolve a physical path for Windows long-path I/O without changing stored names."""
    path = Path(path)
    if os.name != "nt" or str(path).startswith("\\\\?\\"):
        return path
    resolved = str(path.resolve())
    if resolved.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + resolved.lstrip("\\"))
    return Path("\\\\?\\" + resolved)


def load_data(path, env_file=None):
    try:
        load_dotenv(DEFAULT_ENV_FILE if env_file is None else env_file)
        with Path(path).open(encoding="utf-8") as stream:
            return resolve_environment(yaml.safe_load(stream))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"Cannot read {path}: {exc}") from exc


def inside(root, relative):
    root = Path(root).resolve()
    windows = PureWindowsPath(relative)
    value = Path(str(relative).replace("\\", "/"))
    if windows.drive or windows.root or value.is_absolute() or ".." in value.parts:
        raise BoundaryError(f"Expected a project-relative path: {relative}")
    target = (root / value).resolve()
    if not target.is_relative_to(root):
        raise BoundaryError(f"Path escapes workspace: {relative}")
    return target


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            if path.suffix == ".json":
                json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            else:
                yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sha256(path):
    digest = hashlib.sha256()
    with filesystem_path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

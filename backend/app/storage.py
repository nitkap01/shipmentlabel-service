"""Filesystem access, confined to LABEL_STORAGE_ROOT (D11).

`label_directory` (the portal's configurable "save directory") is always a
relative subpath under the fixed storage root. Path traversal, absolute
paths, and symlink escapes are rejected.
"""

import re
from pathlib import Path

from app.config import settings


class StoragePathError(ValueError):
    pass


def storage_root() -> Path:
    return Path(settings.label_storage_root).resolve()


def validate_relative_subpath(raw: str) -> str:
    """Raises StoragePathError if `raw` is not a safe relative subpath."""
    if not raw or not raw.strip():
        raise StoragePathError("Directory cannot be blank")

    trimmed = raw.strip()
    # Absoluteness must be checked on the untouched string: stripping a
    # leading '/' first (to tolerate e.g. "labels/" as input) would turn
    # "/etc" into "etc" and silently pass it as "relative".
    if Path(trimmed).is_absolute():
        raise StoragePathError("Directory must be a relative path with no '..'")

    candidate = trimmed.strip("/")
    if not candidate:
        raise StoragePathError("Directory cannot be blank")

    if ".." in Path(candidate).parts:
        raise StoragePathError("Directory must be a relative path with no '..'")

    root = storage_root()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise StoragePathError("Directory resolves outside the storage root")

    return candidate


def resolve_under_root(relative_path: str) -> Path:
    """Resolve a path already stored as relative-to-root (e.g. `labels.pdf_path`)."""
    root = storage_root()
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(root):
        raise StoragePathError("Stored path resolves outside the storage root")
    return resolved


def sanitize_filename_part(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    cleaned = re.sub(r"[^A-Za-z0-9-]", "", value)
    return cleaned or fallback


def write_bytes_under_root(relative_dir: str, filename: str, data: bytes) -> tuple[str, int]:
    """Writes `data` under storage_root()/relative_dir/filename.

    Returns (path_relative_to_root, size_bytes).
    """
    validated_dir = validate_relative_subpath(relative_dir)
    root = storage_root()
    target_dir = (root / validated_dir).resolve()
    if not target_dir.is_relative_to(root):
        raise StoragePathError("Directory resolves outside the storage root")
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path.write_bytes(data)

    relative = target_path.relative_to(root)
    return str(relative), target_path.stat().st_size

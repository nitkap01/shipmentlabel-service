import pytest

from app.storage import (
    StoragePathError,
    resolve_under_root,
    storage_root,
    validate_relative_subpath,
    write_bytes_under_root,
)


def test_valid_subpath_resolves_inside_root():
    cleaned = validate_relative_subpath("labels")
    assert cleaned == "labels"
    resolved = storage_root() / cleaned
    assert resolved.resolve().is_relative_to(storage_root())


def test_nested_valid_subpath():
    assert validate_relative_subpath("GreenShadow/labels") == "GreenShadow/labels"


@pytest.mark.parametrize("bad", ["../..", "../../etc", "/etc", "/etc/passwd", ".."])
def test_traversal_and_absolute_paths_rejected(bad):
    with pytest.raises(StoragePathError):
        validate_relative_subpath(bad)


def test_blank_rejected():
    with pytest.raises(StoragePathError):
        validate_relative_subpath("")
    with pytest.raises(StoragePathError):
        validate_relative_subpath("   ")


def test_symlink_escape_rejected(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "escape").symlink_to(outside)

    monkeypatch.setattr("app.storage.settings.label_storage_root", str(root))

    with pytest.raises(StoragePathError):
        validate_relative_subpath("escape")


def test_write_and_resolve_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr("app.storage.settings.label_storage_root", str(tmp_path))
    relative, size = write_bytes_under_root("labels/2026/08", "test.pdf", b"hello world")
    assert size == len(b"hello world")
    resolved = resolve_under_root(relative)
    assert resolved.exists()
    assert resolved.read_bytes() == b"hello world"


def test_resolve_under_root_rejects_escape(monkeypatch, tmp_path):
    monkeypatch.setattr("app.storage.settings.label_storage_root", str(tmp_path))
    with pytest.raises(StoragePathError):
        resolve_under_root("../../etc/passwd")

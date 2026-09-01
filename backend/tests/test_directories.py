import pytest

ESCAPE_PATHS = [
    "..",
    "../..",
    "../../etc",
    "/etc",
    "/etc/passwd",
    "labels/../..",
    "/",
]

INVALID_FOLDER_NAMES = ["", "   ", "..", ".", "a/b", "../escape", "/etc", ".hidden", "x" * 65]


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    monkeypatch.setattr("app.storage.settings.label_storage_root", str(tmp_path))
    return tmp_path.resolve()


def list_directories(client, path=None):
    params = {} if path is None else {"path": path}
    return client.get("/api/settings/directories", params=params)


def create_directory(client, path, name):
    return client.post("/api/settings/directories", json={"path": path, "name": name})


def test_list_root_when_empty(logged_in_client, storage_root):
    resp = list_directories(logged_in_client)
    assert resp.status_code == 200
    assert resp.json() == {"path": "", "entries": []}


def test_create_folder_then_it_appears_in_root_listing(logged_in_client, storage_root):
    created = create_directory(logged_in_client, "", "labels")
    assert created.status_code == 200
    assert created.json() == {"name": "labels", "path": "labels"}
    assert (storage_root / "labels").is_dir()

    listing = list_directories(logged_in_client)
    assert listing.status_code == 200
    assert listing.json()["entries"] == [{"name": "labels", "path": "labels"}]


def test_create_nested_folder_appears_in_parent_listing(logged_in_client, storage_root):
    assert create_directory(logged_in_client, "", "labels").status_code == 200
    created = create_directory(logged_in_client, "labels", "2026")
    assert created.status_code == 200
    assert created.json() == {"name": "2026", "path": "labels/2026"}

    listing = list_directories(logged_in_client, "labels")
    assert listing.status_code == 200
    assert listing.json() == {"path": "labels", "entries": [{"name": "2026", "path": "labels/2026"}]}


def test_listing_ignores_files_and_sorts_folders(logged_in_client, storage_root):
    (storage_root / "beta").mkdir()
    (storage_root / "Alpha").mkdir()
    (storage_root / "note.txt").write_text("not a folder")

    resp = list_directories(logged_in_client)
    assert resp.status_code == 200
    assert [entry["name"] for entry in resp.json()["entries"]] == ["Alpha", "beta"]


def test_trailing_slash_path_is_normalized(logged_in_client, storage_root):
    (storage_root / "labels").mkdir()
    resp = list_directories(logged_in_client, "labels/")
    assert resp.status_code == 200
    assert resp.json()["path"] == "labels"


def test_list_unknown_path_returns_404(logged_in_client, storage_root):
    resp = list_directories(logged_in_client, "nope")
    assert resp.status_code == 404


def test_create_under_unknown_parent_creates_nothing(logged_in_client, storage_root):
    resp = create_directory(logged_in_client, "missing/deep", "child")
    assert resp.status_code == 404
    assert not (storage_root / "missing").exists()


def test_duplicate_folder_returns_409(logged_in_client, storage_root):
    assert create_directory(logged_in_client, "", "labels").status_code == 200
    resp = create_directory(logged_in_client, "", "labels")
    assert resp.status_code == 409


@pytest.mark.parametrize("bad", ESCAPE_PATHS)
def test_list_rejects_traversal_and_absolute_paths(logged_in_client, storage_root, bad):
    resp = list_directories(logged_in_client, bad)
    assert resp.status_code == 400


@pytest.mark.parametrize("bad", ESCAPE_PATHS)
def test_create_rejects_traversal_and_absolute_parent_paths(logged_in_client, storage_root, bad):
    resp = create_directory(logged_in_client, bad, "child")
    assert resp.status_code == 400


def test_list_rejects_url_encoded_traversal(logged_in_client, storage_root):
    resp = logged_in_client.get("/api/settings/directories?path=..%2F..")
    assert resp.status_code == 400


def test_double_encoded_traversal_is_never_decoded_into_an_escape(logged_in_client, storage_root):
    resp = logged_in_client.get("/api/settings/directories?path=%252e%252e%252f%252e%252e")
    assert resp.status_code == 404


def test_null_byte_in_path_is_rejected(logged_in_client, storage_root):
    assert logged_in_client.get("/api/settings/directories?path=a%00b").status_code == 400
    assert create_directory(logged_in_client, "a\x00b", "child").status_code == 400


def test_symlink_escape_is_hidden_and_not_browsable(logged_in_client, storage_root, tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    (outside / "secrets").mkdir()
    (storage_root / "escape").symlink_to(outside)

    listing = list_directories(logged_in_client)
    assert listing.status_code == 200
    assert listing.json()["entries"] == []

    assert list_directories(logged_in_client, "escape").status_code == 400
    assert list_directories(logged_in_client, "escape/secrets").status_code == 400


def test_create_through_symlink_escape_rejected(logged_in_client, storage_root, tmp_path):
    outside = tmp_path.parent / "outside-create"
    outside.mkdir()
    (storage_root / "escape").symlink_to(outside)

    resp = create_directory(logged_in_client, "escape", "child")
    assert resp.status_code == 400
    assert not (outside / "child").exists()


@pytest.mark.parametrize("bad", INVALID_FOLDER_NAMES)
def test_create_rejects_invalid_folder_names(logged_in_client, storage_root, bad):
    resp = create_directory(logged_in_client, "", bad)
    assert resp.status_code == 400
    assert list(storage_root.iterdir()) == []


def test_picked_folder_is_accepted_as_label_directory(logged_in_client, storage_root):
    assert create_directory(logged_in_client, "", "labels").status_code == 200
    picked = create_directory(logged_in_client, "labels", "2026").json()["path"]

    current = logged_in_client.get("/api/settings").json()
    saved = logged_in_client.put("/api/settings", json={**current, "label_directory": picked})
    assert saved.status_code == 200
    assert saved.json()["label_directory"] == "labels/2026"


def test_list_requires_login(client, storage_root):
    assert list_directories(client).status_code == 401


def test_create_requires_login(client, storage_root):
    assert create_directory(client, "", "labels").status_code == 401
    assert not (storage_root / "labels").exists()

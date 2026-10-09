"""SHIP-8: file manager (browse / download / zip / delete with confirmation) and the backup panel routes."""
import io
import zipfile

import pytest

from app.storage import storage_root
from tests.conftest import make_ship_success

PAYLOAD = {
    "recipient_name": "Jane Doe", "recipient_address1": "123 Main St", "recipient_city": "Newark",
    "recipient_state": "NJ", "recipient_postal_code": "07102", "weight_value": 8, "weight_unit": "oz",
    "declared_value": 10.00,
}


@pytest.fixture
def label(logged_in_client, monkeypatch, fake_png_base64):
    async def fake_ship(environment, body):
        return make_ship_success(fake_png_base64)

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    resp = logged_in_client.post("/api/labels", json=PAYLOAD)
    assert resp.status_code == 200 and resp.json()["pdf_path"]
    return resp.json()


def _folder_of(path: str) -> str:
    return path.rsplit("/", 1)[0]


def test_browse_root_and_month_folder_links_files_to_labels(logged_in_client, label):
    (storage_root() / ".backup").mkdir(exist_ok=True)
    root = logged_in_client.get("/api/files").json()
    names = [f["name"] for f in root["folders"]]
    assert "labels" in names and ".backup" not in names  # hidden folder never shown
    month = logged_in_client.get("/api/files", params={"path": _folder_of(label["pdf_path"])}).json()
    mine = [f for f in month["files"] if f["path"] == label["pdf_path"]]  # other tests leave PDFs in the same folder
    assert len(mine) == 1 and mine[0]["label"]["id"] == label["id"]


def test_download_one_and_zip_of_a_folder(logged_in_client, label):
    one = logged_in_client.get("/api/files/file", params={"path": label["pdf_path"]})
    assert one.status_code == 200 and one.content[:4] == b"%PDF"
    z = logged_in_client.post("/api/files/zip", json={"paths": ["labels"]})
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert label["pdf_path"] in names and all(n.startswith("labels/") for n in names)


@pytest.mark.parametrize("bad", ["../etc/passwd", "/etc/passwd", ".backup/status.json", "labels/../../x", ""])
def test_paths_outside_storage_or_hidden_are_refused(logged_in_client, label, bad):
    assert logged_in_client.get("/api/files/file", params={"path": bad}).status_code in (400, 422)
    assert logged_in_client.post("/api/files/zip", json={"paths": [bad]}).status_code in (400, 422)


def test_delete_needs_confirmation_and_keeps_the_label_record(logged_in_client, label):
    no = logged_in_client.post("/api/files/delete", json={"paths": [label["pdf_path"]], "confirm": "yes"})
    assert no.status_code == 400
    assert (storage_root() / label["pdf_path"]).exists()

    folder = logged_in_client.post("/api/files/delete", json={"paths": ["labels"], "confirm": "DELETE"})
    assert folder.status_code == 400  # folders are never deleted

    ok = logged_in_client.post("/api/files/delete", json={"paths": [label["pdf_path"]], "confirm": "DELETE"})
    assert ok.status_code == 200 and ok.json() == {"deleted": 1, "labels_updated": 1}
    assert not (storage_root() / label["pdf_path"]).exists()
    after = logged_in_client.get(f"/api/labels/{label['id']}").json()
    assert after["status"] == "created" and after["pdf_path"] is None and after["pdf_deleted_at"]


def test_backup_status_request_and_full_download(logged_in_client, label):
    b = storage_root() / ".backup"
    for f in ("request", "status.json", "db-latest.sql.gz"):
        (b / f).unlink(missing_ok=True)
    s = logged_in_client.get("/api/backup").json()
    assert s == {"last": None, "queued": False, "db_copy_available": False}

    assert logged_in_client.post("/api/backup/run").json() == {"queued": True}
    assert (b / "request").exists()
    assert logged_in_client.get("/api/backup").json()["queued"] is True

    (b / "status.json").write_text('{"ok": true, "uploaded_files": 1, "total_files": 1}')
    (b / "db-latest.sql.gz").write_bytes(b"\x1f\x8bfake")
    assert logged_in_client.get("/api/backup").json()["last"]["ok"] is True

    full = logged_in_client.get("/api/backup/download")
    assert full.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(full.content)).namelist()
    assert label["pdf_path"] in names and "database/db-latest.sql.gz" in names
    assert not any(n.startswith(".backup") for n in names)


def test_files_need_login(client):
    assert client.get("/api/files").status_code == 401
    assert client.get("/api/backup/download").status_code == 401

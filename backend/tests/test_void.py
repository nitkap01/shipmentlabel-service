import pytest

from app.epg.client import EPGError
from tests.conftest import make_ship_success

VALID_LABEL_PAYLOAD = {
    "recipient_name": "Jane Doe",
    "recipient_address1": "123 Main St",
    "recipient_city": "Newark",
    "recipient_state": "NJ",
    "recipient_postal_code": "07102",
    "weight_value": 8,
    "weight_unit": "oz",
    "declared_value": 10.00,
}


@pytest.fixture
def created_label(logged_in_client, monkeypatch, fake_png_base64):
    async def fake_ship(environment, body):
        return make_ship_success(fake_png_base64)

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    resp = logged_in_client.post("/api/labels", json=VALID_LABEL_PAYLOAD)
    assert resp.status_code == 200
    label = resp.json()
    assert label["status"] == "created"
    return label


def test_void_flips_status_and_sets_voided_at(logged_in_client, created_label, monkeypatch):
    async def fake_void(environment, unique_reference_id):
        return {"success": True}

    monkeypatch.setattr("app.routers.labels.epg_client.void", fake_void)

    resp = logged_in_client.post(f"/api/labels/{created_label['id']}/void")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "voided"
    assert body["voided_at"] is not None


def test_second_void_is_rejected(logged_in_client, created_label, monkeypatch):
    async def fake_void(environment, unique_reference_id):
        return {"success": True}

    monkeypatch.setattr("app.routers.labels.epg_client.void", fake_void)
    logged_in_client.post(f"/api/labels/{created_label['id']}/void")

    resp = logged_in_client.post(f"/api/labels/{created_label['id']}/void")
    assert resp.status_code == 400


def test_epg_error_leaves_status_unchanged_and_records_void_error(logged_in_client, created_label, monkeypatch):
    async def fake_void(environment, unique_reference_id):
        raise EPGError("EPG is down", status_code=502)

    monkeypatch.setattr("app.routers.labels.epg_client.void", fake_void)

    resp = logged_in_client.post(f"/api/labels/{created_label['id']}/void")
    assert resp.status_code == 502

    detail = logged_in_client.get(f"/api/labels/{created_label['id']}").json()
    assert detail["status"] == "created"
    assert detail["void_error"]


def test_voided_label_still_searchable_and_downloadable(logged_in_client, created_label, monkeypatch):
    async def fake_void(environment, unique_reference_id):
        return {"success": True}

    monkeypatch.setattr("app.routers.labels.epg_client.void", fake_void)
    logged_in_client.post(f"/api/labels/{created_label['id']}/void")

    search = logged_in_client.get("/api/labels", params={"q": "jane"})
    assert search.status_code == 200
    ids = [item["id"] for item in search.json()["items"]]
    assert created_label["id"] in ids

    pdf_resp = logged_in_client.get(f"/api/labels/{created_label['id']}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"

import pytest

from app.epg.client import EPGError, EPGTimeoutError
from app.epg.mapping import extract_close_id, extract_close_reports, parse_open_packages
from tests.conftest import make_ship_failure, make_ship_success

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


# ---- parse_open_packages (F1, F2) ----


@pytest.mark.parametrize("raw", [None, [], {}])
def test_parse_open_packages_empty_inputs_return_empty_list(raw):
    assert parse_open_packages(raw) == []


def test_parse_open_packages_documented_array_shape():
    raw = [{"accountNumber": "11191", "packageCount": 3}]
    assert parse_open_packages(raw) == [{"account_number": "11191", "package_count": 3}]


def test_parse_open_packages_tolerates_bare_object():
    raw = {"accountNumber": "11191", "packageCount": 5}
    assert parse_open_packages(raw) == [{"account_number": "11191", "package_count": 5}]


def test_parse_open_packages_ignores_non_dict_items():
    assert parse_open_packages(["not-a-dict", 42]) == []


# ---- extract_close_id / extract_close_reports (F6) ----


def test_extract_close_id_top_level_camel_case():
    assert extract_close_id({"closeId": "abc-123"}) == "abc-123"


def test_extract_close_id_top_level_pascal_case():
    assert extract_close_id({"CloseId": "abc-123"}) == "abc-123"


def test_extract_close_id_nested_under_package():
    assert extract_close_id({"package": {"closeId": "nested-1"}}) == "nested-1"


def test_extract_close_id_returns_none_when_absent():
    assert extract_close_id({"somethingElse": True}) is None
    assert extract_close_id(None) is None


def test_extract_close_reports_top_level_and_nested_and_absent():
    assert extract_close_reports({"closeReports": ["r1"]}) == ["r1"]
    assert extract_close_reports({"package": {"CloseReports": ["r2"]}}) == ["r2"]
    assert extract_close_reports({}) is None


# ---- HTTP: open_only filter ----


@pytest.fixture
def two_created_labels(logged_in_client, monkeypatch, fake_png_base64):
    counter = {"n": 0}

    async def fake_ship(environment, body):
        counter["n"] += 1
        return make_ship_success(fake_png_base64, tracking=f"T{counter['n']}", unique_ref=f"U{counter['n']}")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    ids = []
    for _ in range(2):
        resp = logged_in_client.post("/api/labels", json=VALID_LABEL_PAYLOAD)
        assert resp.status_code == 200
        ids.append(resp.json()["id"])
    return ids


def test_open_only_returns_created_labels(logged_in_client, two_created_labels):
    resp = logged_in_client.get("/api/labels", params={"open_only": "true"})
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == set(two_created_labels)


def test_voiding_a_label_removes_it_from_open_list(logged_in_client, two_created_labels, monkeypatch):
    async def fake_void(environment, unique_reference_id):
        return {"success": True}

    monkeypatch.setattr("app.routers.labels.epg_client.void", fake_void)
    first_id = two_created_labels[0]
    resp = logged_in_client.post(f"/api/labels/{first_id}/void")
    assert resp.status_code == 200

    resp = logged_in_client.get("/api/labels", params={"open_only": "true"})
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {two_created_labels[1]}


def test_failed_and_pending_labels_never_appear_in_open_list(logged_in_client, monkeypatch):
    async def fake_ship_failure(environment, body):
        return make_ship_failure()

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship_failure)
    failed_resp = logged_in_client.post("/api/labels", json=VALID_LABEL_PAYLOAD)
    assert failed_resp.json()["status"] == "failed"

    async def fake_ship_timeout(environment, body):
        raise EPGTimeoutError("timed out")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship_timeout)
    pending_resp = logged_in_client.post("/api/labels", json=VALID_LABEL_PAYLOAD)
    assert pending_resp.json()["status"] == "pending"

    resp = logged_in_client.get("/api/labels", params={"open_only": "true"})
    ids = {item["id"] for item in resp.json()["items"]}
    assert failed_resp.json()["id"] not in ids
    assert pending_resp.json()["id"] not in ids


# ---- GET /api/manifest/open (D33) ----


def test_open_summary_survives_epg_timeout(logged_in_client, two_created_labels, monkeypatch):
    async def fake_list_open(environment):
        raise EPGTimeoutError("connection timed out")

    monkeypatch.setattr("app.routers.manifest.epg_client.list_open", fake_list_open)

    resp = logged_in_client.get("/api/manifest/open")
    assert resp.status_code == 200
    body = resp.json()
    assert body["open_count"] == len(two_created_labels)
    assert body["epg_error"]
    assert body["epg_package_count"] is None


def test_open_summary_survives_epg_error(logged_in_client, monkeypatch):
    async def fake_list_open(environment):
        raise EPGError("EPG is down", status_code=502)

    monkeypatch.setattr("app.routers.manifest.epg_client.list_open", fake_list_open)

    resp = logged_in_client.get("/api/manifest/open")
    assert resp.status_code == 200
    assert resp.json()["epg_error"]


def test_open_summary_reports_epg_account_number_and_flags_mismatch(logged_in_client, monkeypatch, fake_png_base64):
    async def fake_ship(environment, body):
        response, quota = make_ship_success(fake_png_base64)
        response["package"]["rates"] = [{"accountNumber": "11191"}]
        return response, quota

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    create_resp = logged_in_client.post("/api/labels", json=VALID_LABEL_PAYLOAD)
    assert create_resp.status_code == 200

    async def fake_list_open(environment):
        return [{"accountNumber": "99999", "packageCount": 1}], {"x-quota-available": "9"}

    monkeypatch.setattr("app.routers.manifest.epg_client.list_open", fake_list_open)

    resp = logged_in_client.get("/api/manifest/open")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured_account_number"] == "11191"
    assert body["epg_account_number"] == "99999"
    assert body["configured_account_number"] != body["epg_account_number"]


def test_open_summary_204_shaped_response_reports_zero_open_at_epg(logged_in_client, monkeypatch):
    async def fake_list_open(environment):
        return [], {"x-quota-available": "9"}

    monkeypatch.setattr("app.routers.manifest.epg_client.list_open", fake_list_open)

    resp = logged_in_client.get("/api/manifest/open")
    assert resp.status_code == 200
    assert resp.json()["epg_package_count"] == 0
    assert resp.json()["epg_error"] is None


# ---- Auth ----


def test_manifest_open_requires_login(client):
    assert client.get("/api/manifest/open").status_code == 401

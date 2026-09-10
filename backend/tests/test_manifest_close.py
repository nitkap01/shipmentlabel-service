import pytest

from app.epg.client import EPGError, EPGTimeoutError
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


def _ship_with_account(fake_png_base64: str, account_number: str = "11191", tracking: str = "T1", unique_ref: str = "U1"):
    response, quota = make_ship_success(fake_png_base64, tracking=tracking, unique_ref=unique_ref)
    response["package"]["rates"] = [{"accountNumber": account_number}]
    return response, quota


@pytest.fixture
def two_open_labels(logged_in_client, monkeypatch, fake_png_base64):
    counter = {"n": 0}

    async def fake_ship(environment, body):
        counter["n"] += 1
        return _ship_with_account(fake_png_base64, tracking=f"T{counter['n']}", unique_ref=f"U{counter['n']}")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    ids = []
    for _ in range(2):
        resp = logged_in_client.post("/api/labels", json=VALID_LABEL_PAYLOAD)
        assert resp.status_code == 200
        ids.append(resp.json()["id"])
    return ids


def test_close_without_account_number_returns_400_and_never_calls_epg(logged_in_client, monkeypatch):
    calls = {"n": 0}

    async def fake_close(environment, account_number):
        calls["n"] += 1
        return {"wasSuccessful": True}, {}

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 400
    assert calls["n"] == 0


def test_full_close_flow_attaches_labels_and_records_history(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close(environment, account_number):
        assert account_number == "11191"
        return (
            {"wasSuccessful": True, "closeId": "close-abc", "closeReports": ["report-1"]},
            {"x-quota-available": "8"},
        )

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["close_id"] == "close-abc"
    assert body["close_reports"] == ["report-1"]
    assert body["label_count"] == 2
    close_id = body["id"]

    open_resp = logged_in_client.get("/api/labels", params={"open_only": "true"})
    assert open_resp.json()["items"] == []

    history_resp = logged_in_client.get("/api/manifest/closes")
    assert history_resp.status_code == 200
    assert len(history_resp.json()) == 1
    assert history_resp.json()[0]["label_count"] == 2

    detail_resp = logged_in_client.get(f"/api/manifest/closes/{close_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["close_id"] == "close-abc"

    attached_resp = logged_in_client.get("/api/labels", params={"manifest_close_id": close_id})
    assert attached_resp.status_code == 200
    assert {item["id"] for item in attached_resp.json()["items"]} == set(two_open_labels)


def test_epg_error_marks_close_failed_and_leaves_labels_open(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close(environment, account_number):
        raise EPGError("EPG is down", status_code=502)

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 502

    history = logged_in_client.get("/api/manifest/closes").json()
    assert history[0]["status"] == "failed"

    open_ids = {item["id"] for item in logged_in_client.get("/api/labels", params={"open_only": "true"}).json()["items"]}
    assert open_ids == set(two_open_labels)


def test_close_was_successful_false_marks_failed_and_leaves_labels_open(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close(environment, account_number):
        return {"wasSuccessful": False, "responseMessage": "close rejected"}, {}

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 502

    history = logged_in_client.get("/api/manifest/closes").json()
    assert history[0]["status"] == "failed"

    open_ids = {item["id"] for item in logged_in_client.get("/api/labels", params={"open_only": "true"}).json()["items"]}
    assert open_ids == set(two_open_labels)


def test_timeout_leaves_close_pending_and_labels_open_and_is_persisted(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close(environment, account_number):
        raise EPGTimeoutError("connection timed out")

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 502

    history = logged_in_client.get("/api/manifest/closes").json()
    assert len(history) == 1
    assert history[0]["status"] == "pending"

    open_ids = {item["id"] for item in logged_in_client.get("/api/labels", params={"open_only": "true"}).json()["items"]}
    assert open_ids == set(two_open_labels)


def test_ambiguous_empty_close_response_leaves_close_pending_for_manual_resolution(
    logged_in_client, two_open_labels, monkeypatch
):
    async def fake_close(environment, account_number):
        return {}, {}

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 502

    history = logged_in_client.get("/api/manifest/closes").json()
    assert len(history) == 1
    assert history[0]["status"] == "pending"

    open_ids = {item["id"] for item in logged_in_client.get("/api/labels", params={"open_only": "true"}).json()["items"]}
    assert open_ids == set(two_open_labels)


def test_epg_error_message_reaches_response_and_persisted_history(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close(environment, account_number):
        raise EPGError("0 active unclosed packages were found for the given account number", status_code=400)

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 502
    assert "0 active unclosed packages" in resp.json()["detail"]

    history = logged_in_client.get("/api/manifest/closes").json()
    assert history[0]["error_message"] == "0 active unclosed packages were found for the given account number"


def test_second_close_while_pending_returns_409(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close_timeout(environment, account_number):
        raise EPGTimeoutError("connection timed out")

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close_timeout)
    first = logged_in_client.post("/api/manifest/closes")
    assert first.status_code == 502

    resp = logged_in_client.post("/api/manifest/closes")
    assert resp.status_code == 409


def test_resolve_completed_attaches_exactly_snapshotted_candidates(
    logged_in_client, two_open_labels, monkeypatch, fake_png_base64
):
    async def fake_close_timeout(environment, account_number):
        raise EPGTimeoutError("connection timed out")

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close_timeout)
    logged_in_client.post("/api/manifest/closes")
    close_id = logged_in_client.get("/api/manifest/closes").json()[0]["id"]

    async def fake_ship(environment, body):
        return _ship_with_account(fake_png_base64, tracking="T99", unique_ref="U99")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    late_label = logged_in_client.post("/api/labels", json=VALID_LABEL_PAYLOAD).json()

    resolve_resp = logged_in_client.post(f"/api/manifest/closes/{close_id}/resolve", json={"outcome": "completed"})
    assert resolve_resp.status_code == 200
    body = resolve_resp.json()
    assert body["status"] == "completed"
    assert body["resolved_manually"] is True
    assert set(body["candidate_label_ids"]) == set(two_open_labels)

    attached = logged_in_client.get("/api/labels", params={"manifest_close_id": close_id}).json()
    attached_ids = {item["id"] for item in attached["items"]}
    assert attached_ids == set(two_open_labels)
    assert late_label["id"] not in attached_ids

    open_ids = {
        item["id"] for item in logged_in_client.get("/api/labels", params={"open_only": "true"}).json()["items"]
    }
    assert open_ids == {late_label["id"]}


def test_resolve_failed_leaves_labels_open(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close_timeout(environment, account_number):
        raise EPGTimeoutError("connection timed out")

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close_timeout)
    logged_in_client.post("/api/manifest/closes")
    close_id = logged_in_client.get("/api/manifest/closes").json()[0]["id"]

    resolve_resp = logged_in_client.post(f"/api/manifest/closes/{close_id}/resolve", json={"outcome": "failed"})
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "failed"

    open_ids = {
        item["id"] for item in logged_in_client.get("/api/labels", params={"open_only": "true"}).json()["items"]
    }
    assert open_ids == set(two_open_labels)


def test_resolving_already_terminal_close_returns_400(logged_in_client, two_open_labels, monkeypatch):
    async def fake_close(environment, account_number):
        return {"wasSuccessful": True, "closeId": "c1", "closeReports": []}, {}

    monkeypatch.setattr("app.routers.manifest.epg_client.close_manifest", fake_close)
    logged_in_client.post("/api/manifest/closes")
    close_id = logged_in_client.get("/api/manifest/closes").json()[0]["id"]

    resp = logged_in_client.post(f"/api/manifest/closes/{close_id}/resolve", json={"outcome": "completed"})
    assert resp.status_code == 400


def test_resolve_not_found_returns_404(logged_in_client):
    resp = logged_in_client.post("/api/manifest/closes/999999/resolve", json={"outcome": "completed"})
    assert resp.status_code == 404


def test_manifest_endpoints_require_login(client):
    assert client.get("/api/manifest/open").status_code == 401
    assert client.post("/api/manifest/closes").status_code == 401
    assert client.get("/api/manifest/closes").status_code == 401
    assert client.get("/api/manifest/closes/1").status_code == 401
    assert client.post("/api/manifest/closes/1/resolve", json={"outcome": "completed"}).status_code == 401

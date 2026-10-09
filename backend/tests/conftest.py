import base64
import io
import os
import tempfile

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://nitinkapoor@localhost:5432/shipmentlabel_test"
)
os.environ.setdefault("EPG_API_KEY_SANDBOX", "test-dummy-key")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password-0123")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-0123456789abcdef")
os.environ.setdefault("LABEL_STORAGE_ROOT", tempfile.mkdtemp(prefix="shipmentlabel-tests-"))

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.db import SessionLocal, run_migrations
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    import asyncio

    asyncio.run(run_migrations())


@pytest.fixture(autouse=True)
async def _reset_db():
    async with SessionLocal() as db:
        await db.execute(
            text("TRUNCATE bulk_run_rows, labels, bulk_runs, manifest_closes RESTART IDENTITY CASCADE")
        )
        await db.execute(
            text(
                "UPDATE app_settings SET from_name='Navdeep Bajaj', from_company='Green Shadow Enterprises', "
                "from_address1='293 Whitehead Rd', from_address2=NULL, from_city='Trenton', from_state='NJ', "
                "from_postal_code='08619-3250', label_directory='labels', default_service_code='EP05', "
                "epg_environment='sandbox', epg_account_number_sandbox=NULL, "
                "epg_account_number_production=NULL WHERE id = 1"
            )
        )
        await db.commit()
    yield


@pytest.fixture(autouse=True)
def _duplicate_guard_off_unless_marked(request, monkeypatch):
    """SHIP-3's duplicate guard refuses identical labels bought minutes apart. Many older tests buy identical labels
    on purpose (to test something else), so the guard is off for them; tests marked `duplicate_guard` keep it on."""
    if request.node.get_closest_marker("duplicate_guard") is None:
        async def no_duplicate(*args, **kwargs):
            return None

        monkeypatch.setattr("app.labels_service.find_recent_duplicate", no_duplicate)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def logged_in_client(client):
    resp = client.post("/api/auth/login", json={"password": "test-admin-password-0123"})
    assert resp.status_code == 200
    return client


@pytest.fixture
def fake_png_bytes() -> bytes:
    img = Image.new("RGB", (812, 1218), color="white")  # ~4x6in @ 203dpi
    out = io.BytesIO()
    img.save(out, format="PNG", dpi=(203, 203))
    return out.getvalue()


@pytest.fixture
def fake_png_base64(fake_png_bytes) -> str:
    return base64.b64encode(fake_png_bytes).decode()


def make_ship_success(fake_png_base64: str, tracking: str = "EPGTEST123", unique_ref: str = "unique-ref-abc"):
    return (
        {
            "wasSuccessful": True,
            "responseMessage": "Shipping Successful!",
            "errors": None,
            "package": {
                "uniqueReferenceId": unique_ref,
                "trackingNumber": tracking,
                "labels": [fake_png_base64],
            },
        },
        {"x-quota-available": "9"},
    )


def make_ship_failure(message: str = "EPG EP05: could not process shipment"):
    return (
        {"wasSuccessful": False, "responseMessage": "", "errors": [{"message": message}], "package": None},
        {"x-quota-available": "9"},
    )

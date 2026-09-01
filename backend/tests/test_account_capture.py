"""Auto-capture of the EPG account number (D28, revised 2026-08-31).

There is no admin-typed account-number field. Every successful `ship` call
reads `accountNumber` out of the response and self-heals it into the
matching per-environment `app_settings` column (F3).
"""

from decimal import Decimal

from app.db import SessionLocal
from app.labels_service import create_label, get_settings_row
from tests.conftest import make_ship_success

LABEL_FIELDS = {
    "recipient_name": "Jane Doe",
    "recipient_company": None,
    "recipient_address1": "123 Main St",
    "recipient_address2": None,
    "recipient_city": "Newark",
    "recipient_state": "NJ",
    "recipient_postal_code": "07102",
    "recipient_phone": None,
    "recipient_email": None,
    "weight_value": Decimal("8"),
    "weight_unit": "oz",
    "length_value": None,
    "width_value": None,
    "height_value": None,
    "dimension_unit": None,
    "declared_value": Decimal("10.00"),
    "reference1": None,
    "service_code": "EP05",
}


def _ship_success_with_account(fake_png_base64: str, account_number: str, tracking: str, unique_ref: str):
    response, quota = make_ship_success(fake_png_base64, tracking=tracking, unique_ref=unique_ref)
    response["package"]["rates"] = [{"accountNumber": account_number}]
    return response, quota


async def test_ship_success_captures_account_number_into_sandbox_column(monkeypatch, fake_png_base64):
    async def fake_ship(environment, body):
        return _ship_success_with_account(fake_png_base64, "11191", "T1", "U1")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)

    async with SessionLocal() as db:
        settings_row = await get_settings_row(db)
        assert settings_row.epg_account_number_sandbox is None

        label = await create_label(
            db, fields=LABEL_FIELDS, source="single", bulk_run_id=None, settings_row=settings_row
        )
        await db.commit()

        assert label.status == "created"
        await db.refresh(settings_row)
        assert settings_row.epg_account_number_sandbox == "11191"
        assert settings_row.epg_account_number_production is None


async def test_differing_account_number_on_later_call_self_heals_not_first_value_wins(
    monkeypatch, fake_png_base64
):
    calls = {"n": 0}

    async def fake_ship(environment, body):
        calls["n"] += 1
        account = "11191" if calls["n"] == 1 else "99999"
        return _ship_success_with_account(fake_png_base64, account, f"T{calls['n']}", f"U{calls['n']}")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)

    async with SessionLocal() as db:
        settings_row = await get_settings_row(db)
        await create_label(db, fields=LABEL_FIELDS, source="single", bulk_run_id=None, settings_row=settings_row)
        await db.commit()
        await db.refresh(settings_row)
        assert settings_row.epg_account_number_sandbox == "11191"

        await create_label(db, fields=LABEL_FIELDS, source="single", bulk_run_id=None, settings_row=settings_row)
        await db.commit()
        await db.refresh(settings_row)
        assert settings_row.epg_account_number_sandbox == "99999"


async def test_no_account_number_in_response_leaves_column_untouched(monkeypatch, fake_png_base64):
    async def fake_ship(environment, body):
        return make_ship_success(fake_png_base64)  # no rates/accountNumber field at all

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)

    async with SessionLocal() as db:
        settings_row = await get_settings_row(db)
        await create_label(db, fields=LABEL_FIELDS, source="single", bulk_run_id=None, settings_row=settings_row)
        await db.commit()
        await db.refresh(settings_row)
        assert settings_row.epg_account_number_sandbox is None


async def test_production_call_writes_production_column_never_sandbox(monkeypatch, fake_png_base64):
    async def fake_ship(environment, body):
        assert environment == "production"
        return _ship_success_with_account(fake_png_base64, "11191", "T1", "U1")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)

    async with SessionLocal() as db:
        settings_row = await get_settings_row(db)
        settings_row.epg_environment = "production"
        await db.commit()
        await db.refresh(settings_row)

        await create_label(db, fields=LABEL_FIELDS, source="single", bulk_run_id=None, settings_row=settings_row)
        await db.commit()
        await db.refresh(settings_row)

        assert settings_row.epg_account_number_production == "11191"
        assert settings_row.epg_account_number_sandbox is None

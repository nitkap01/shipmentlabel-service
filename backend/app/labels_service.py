"""Shared single-label creation path (D2, D12): used by both the single-label
API and the bulk runner, so there is exactly one place that talks to EPG and
writes a `labels` row.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.epg import client as epg_client
from app.epg import mapping as epg_mapping
from app.models import AppSettings, Label
from app.pdf import png_bytes_to_pdf_bytes
from app.storage import sanitize_filename_part, write_bytes_under_root
from app.units import to_inches, to_ounces


def digits_only(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits or None


async def create_label(
    db: AsyncSession,
    *,
    fields: dict,
    source: str,
    bulk_run_id: int | None,
    settings_row: AppSettings,
    from_override: dict | None = None,
) -> Label:
    weight_oz = to_ounces(fields["weight_value"], fields["weight_unit"])

    length_in = width_in = height_in = None
    if fields.get("length_value") is not None:
        length_in = to_inches(fields["length_value"], fields["dimension_unit"])
        width_in = to_inches(fields["width_value"], fields["dimension_unit"])
        height_in = to_inches(fields["height_value"], fields["dimension_unit"])

    from_block = from_override or {
        "name": settings_row.from_name,
        "company": settings_row.from_company,
        "address1": settings_row.from_address1,
        "address2": settings_row.from_address2,
        "city": settings_row.from_city,
        "state": settings_row.from_state,
        "postal_code": settings_row.from_postal_code,
        "phone": settings_row.from_phone,
        "email": settings_row.from_email,
    }

    label = Label(
        created_at=datetime.now(timezone.utc),
        status="pending",
        source=source,
        bulk_run_id=bulk_run_id,
        epg_environment=settings_row.epg_environment,
        service_code=fields["service_code"],
        recipient_name=fields["recipient_name"],
        recipient_company=fields.get("recipient_company"),
        recipient_address1=fields["recipient_address1"],
        recipient_address2=fields.get("recipient_address2"),
        recipient_city=fields["recipient_city"],
        recipient_state=fields["recipient_state"],
        recipient_postal_code=fields["recipient_postal_code"],
        recipient_country="US",
        recipient_phone=fields.get("recipient_phone"),
        recipient_phone_digits=digits_only(fields.get("recipient_phone")),
        recipient_email=fields.get("recipient_email"),
        from_name=from_block.get("name"),
        from_company=from_block["company"],
        from_address1=from_block["address1"],
        from_address2=from_block.get("address2"),
        from_city=from_block["city"],
        from_state=from_block["state"],
        from_postal_code=from_block["postal_code"],
        from_country="US",
        from_phone=from_block.get("phone"),
        from_email=from_block.get("email"),
        weight_value=fields["weight_value"],
        weight_unit=fields["weight_unit"],
        weight_oz=weight_oz,
        length_value=fields.get("length_value"),
        width_value=fields.get("width_value"),
        height_value=fields.get("height_value"),
        dimension_unit=fields.get("dimension_unit"),
        length_in=length_in,
        width_in=width_in,
        height_in=height_in,
        declared_value=fields["declared_value"],
        currency_code="USD",
        reference1=fields.get("reference1"),
        notes=fields.get("notes"),
    )
    db.add(label)
    await db.flush()  # assign label.id before building epg_reference_id

    epg_reference_id = f"SL-{label.id}"
    request_body = epg_mapping.build_ship_request(
        {
            **fields,
            "currency_code": label.currency_code,
            "weight_oz": weight_oz,
            "length_in": length_in,
            "width_in": width_in,
            "height_in": height_in,
            "from_name": from_block.get("name"),
            "from_company": from_block["company"],
            "from_address1": from_block["address1"],
            "from_address2": from_block.get("address2"),
            "from_city": from_block["city"],
            "from_state": from_block["state"],
            "from_postal_code": from_block["postal_code"],
            "from_country": "US",
            "from_phone": from_block.get("phone"),
            "from_email": from_block.get("email"),
            "epg_reference_id": epg_reference_id,
        }
    )
    label.epg_request_json = request_body

    try:
        response, quota = await epg_client.ship(settings_row.epg_environment, request_body)
    except epg_client.EPGTimeoutError as exc:
        # Ambiguous: EPG may or may not have created the shipment. Stays
        # `pending` ("needs checking") rather than `failed`, so it is never
        # mistaken for a safe-to-resubmit row (D8).
        label.epg_error_message = str(exc)
        await db.flush()
        return label
    except epg_client.EPGError as exc:
        label.status = "failed"
        label.epg_error_message = str(exc)
        label.epg_error_code = str(exc.status_code) if exc.status_code else None
        await db.flush()
        return label

    label.epg_response_json = epg_mapping.strip_image_payload(response)
    await mirror_quota(db, settings_row, quota)
    await capture_account_number(db, settings_row, settings_row.epg_environment, response)

    if not epg_mapping.is_success(response):
        _, message = epg_mapping.extract_error(response)
        label.status = "failed"
        label.epg_error_message = message
        await db.flush()
        return label

    label.tracking_number = epg_mapping.extract_tracking_number(response)
    label.unique_reference_id = epg_mapping.extract_unique_reference_id(response)

    try:
        png_bytes = epg_mapping.extract_label_png(response)
        pdf_bytes = png_bytes_to_pdf_bytes(png_bytes)
        tracking_part = sanitize_filename_part(label.tracking_number, "notrack")
        date_part = label.created_at.strftime("%Y-%m-%d")
        year_part = label.created_at.strftime("%Y")
        month_part = label.created_at.strftime("%m")
        relative_dir = f"{settings_row.label_directory}/{year_part}/{month_part}"
        filename = f"{date_part}_{tracking_part}_{label.id}.pdf"
        pdf_path, pdf_size = write_bytes_under_root(relative_dir, filename, pdf_bytes)
        label.pdf_path = pdf_path
        label.pdf_size_bytes = pdf_size
        label.status = "created"
    except Exception as exc:  # PNG/PDF/storage failure after a real purchase: needs checking, not silently lost
        label.status = "pending"
        label.epg_error_message = f"Label purchased but PDF pipeline failed: {exc}"

    await db.flush()
    return label


async def mirror_quota(db: AsyncSession, settings_row: AppSettings, quota: dict[str, str]) -> None:
    available = quota.get("x-quota-available") or quota.get("X-Quota-Available")
    if available is None:
        return
    try:
        settings_row.last_quota_available = int(available)
    except ValueError:
        return
    settings_row.last_quota_checked_at = datetime.now(timezone.utc)
    await db.flush()


async def capture_account_number(
    db: AsyncSession, settings_row: AppSettings, environment: str, response: dict
) -> None:
    """Auto-capture (revised D28): every successful `ship` (and `rate`, were
    it ever called — it currently isn't, see the manifest close task doc)
    reads `accountNumber` out of the response and self-heals it into the
    per-environment settings column, creating it if unset and overwriting it
    if the value changed. Never cross-writes sandbox/production.
    """
    account_number = epg_mapping.extract_account_number(response)
    if not account_number:
        return
    column = "epg_account_number_sandbox" if environment == "sandbox" else "epg_account_number_production"
    if getattr(settings_row, column) != account_number:
        setattr(settings_row, column, account_number)
        await db.flush()


async def get_settings_row(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    return result.scalar_one()

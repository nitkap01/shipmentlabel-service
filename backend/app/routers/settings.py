from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.db import get_db
from app.labels_service import get_settings_row
from app.schemas import SettingsOut, SettingsUpdate
from app.security import require_admin
from app.storage import StoragePathError, validate_relative_subpath

router = APIRouter(dependencies=[Depends(require_admin)])

VALID_SERVICE_CODES = {"EP03", "EP05"}


def _available_environments() -> list[str]:
    envs = []
    if app_settings.epg_api_key_sandbox:
        envs.append("sandbox")
    if app_settings.epg_api_key_production:
        envs.append("production")
    return envs


@router.get("/settings", response_model=SettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    row = await get_settings_row(db)
    return SettingsOut(
        **{c: getattr(row, c) for c in SettingsOut.model_fields if hasattr(row, c)},
        available_environments=_available_environments(),
    )


@router.put("/settings", response_model=SettingsOut)
async def update_settings(payload: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    row = await get_settings_row(db)

    if payload.default_service_code not in VALID_SERVICE_CODES:
        raise HTTPException(status_code=400, detail="default_service_code must be EP03 or EP05")

    available = _available_environments()
    if payload.epg_environment not in available:
        raise HTTPException(
            status_code=400,
            detail=f"epg_environment '{payload.epg_environment}' has no API key configured",
        )

    try:
        clean_directory = validate_relative_subpath(payload.label_directory)
    except StoragePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    row.from_name = payload.from_name
    row.from_company = payload.from_company
    row.from_address1 = payload.from_address1
    row.from_address2 = payload.from_address2
    row.from_city = payload.from_city
    row.from_state = payload.from_state
    row.from_postal_code = payload.from_postal_code
    row.from_phone = payload.from_phone
    row.from_email = payload.from_email
    row.label_directory = clean_directory
    row.default_service_code = payload.default_service_code
    row.epg_environment = payload.epg_environment

    await db.commit()
    await db.refresh(row)

    return SettingsOut(
        **{c: getattr(row, c) for c in SettingsOut.model_fields if hasattr(row, c)},
        available_environments=_available_environments(),
    )

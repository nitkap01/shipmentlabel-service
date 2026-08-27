import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.db import get_db
from app.epg import client as epg_client
from app.labels_service import create_label, get_settings_row
from app.models import Label
from app.schemas import LabelCreateRequest, LabelListResponse, LabelOut, LabelStats
from app.security import require_admin
from app.storage import StoragePathError, resolve_under_root

router = APIRouter(dependencies=[Depends(require_admin)])

APP_TZ = ZoneInfo(app_settings.app_timezone)


@router.post("/labels", response_model=LabelOut)
async def create_single_label(payload: LabelCreateRequest, db: AsyncSession = Depends(get_db)):
    settings_row = await get_settings_row(db)

    if payload.length_value is not None and payload.dimension_unit is None:
        raise HTTPException(status_code=400, detail="dimension_unit is required when dimensions are given")

    fields = payload.model_dump(exclude={"service_code", "from_override"})
    fields["service_code"] = payload.service_code or settings_row.default_service_code

    from_override = None
    if payload.from_override:
        override = payload.from_override
        from_override = {
            "name": override.name,
            "company": override.company,
            "address1": override.address1,
            "address2": override.address2,
            "city": override.city,
            "state": override.state,
            "postal_code": override.postal_code,
            "phone": override.phone,
            "email": override.email,
        }

    label = await create_label(
        db,
        fields=fields,
        source="single",
        bulk_run_id=None,
        settings_row=settings_row,
        from_override=from_override,
    )
    await db.commit()
    await db.refresh(label)
    return label


@router.get("/labels", response_model=LabelListResponse)
async def list_labels(
    q: str | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    status: str | None = None,
    bulk_run_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
    db: AsyncSession = Depends(get_db),
):
    query = select(Label)
    count_query = select(func.count()).select_from(Label)

    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(Label.search_text.ilike(pattern))
        count_query = count_query.where(Label.search_text.ilike(pattern))
    if status:
        query = query.where(Label.status == status)
        count_query = count_query.where(Label.status == status)
    if bulk_run_id:
        query = query.where(Label.bulk_run_id == bulk_run_id)
        count_query = count_query.where(Label.bulk_run_id == bulk_run_id)
    if from_date:
        start = datetime.datetime.combine(from_date, datetime.time.min, tzinfo=APP_TZ)
        query = query.where(Label.created_at >= start)
        count_query = count_query.where(Label.created_at >= start)
    if to_date:
        end = datetime.datetime.combine(to_date, datetime.time.max, tzinfo=APP_TZ)
        query = query.where(Label.created_at <= end)
        count_query = count_query.where(Label.created_at <= end)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Label.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return LabelListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/labels/stats", response_model=LabelStats)
async def label_stats(db: AsyncSession = Depends(get_db)):
    now = datetime.datetime.now(APP_TZ)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total = (await db.execute(select(func.count()).select_from(Label))).scalar_one()
    this_month = (
        await db.execute(
            select(func.count()).select_from(Label).where(Label.created_at >= month_start)
        )
    ).scalar_one()
    voided = (
        await db.execute(select(func.count()).select_from(Label).where(Label.status == "voided"))
    ).scalar_one()
    needs_checking = (
        await db.execute(select(func.count()).select_from(Label).where(Label.status == "pending"))
    ).scalar_one()

    return LabelStats(total=total, this_month=this_month, voided=voided, needs_checking=needs_checking)


@router.get("/labels/{label_id}", response_model=LabelOut)
async def get_label(label_id: int, db: AsyncSession = Depends(get_db)):
    label = await db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    return label


@router.get("/labels/{label_id}/pdf")
async def download_label_pdf(label_id: int, db: AsyncSession = Depends(get_db)):
    label = await db.get(Label, label_id)
    if not label or not label.pdf_path:
        raise HTTPException(status_code=404, detail="Label PDF not found")
    try:
        path = resolve_under_root(label.pdf_path)
    except StoragePathError:
        raise HTTPException(status_code=404, detail="Label PDF not found")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Label PDF not found on disk")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.post("/labels/{label_id}/void", response_model=LabelOut)
async def void_label(label_id: int, db: AsyncSession = Depends(get_db)):
    label = await db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    if label.status == "voided":
        raise HTTPException(status_code=400, detail="Label is already voided")
    if not label.unique_reference_id:
        raise HTTPException(status_code=400, detail="Label has no uniqueReferenceId to void")

    settings_row = await get_settings_row(db)
    try:
        await epg_client.void(settings_row.epg_environment, label.unique_reference_id)
    except epg_client.EPGError as exc:
        label.void_error = str(exc)
        await db.commit()
        await db.refresh(label)
        raise HTTPException(status_code=502, detail=f"EPG void failed: {exc}")

    label.status = "voided"
    label.voided_at = datetime.datetime.now(datetime.timezone.utc)
    label.void_error = None
    await db.commit()
    await db.refresh(label)
    return label

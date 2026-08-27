import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bulk.parse import HeaderMismatchError, parse_workbook
from app.bulk.report import build_labels_zip, build_report_xlsx
from app.bulk.template import generate_blank_template
from app.config import settings as app_settings
from app.db import get_db
from app.labels_service import get_settings_row
from app.models import BulkRun, BulkRunRow, Label
from app.schemas import BulkRowError, BulkRunOut, BulkUploadResponse
from app.security import require_admin
from app.storage import write_bytes_under_root
from app.units import DIMENSION_UNITS, WEIGHT_UNITS

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/bulk/template")
async def download_template():
    content = generate_blank_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=shipment_label_template.xlsx"},
    )


@router.post("/bulk/uploads", response_model=BulkUploadResponse)
async def upload_bulk_file(
    file: UploadFile = File(...),
    weight_unit_override: str | None = Form(default=None),
    dimension_unit_override: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    if weight_unit_override and weight_unit_override not in WEIGHT_UNITS:
        raise HTTPException(status_code=400, detail="Invalid weight_unit_override")
    if dimension_unit_override and dimension_unit_override not in DIMENSION_UNITS:
        raise HTTPException(status_code=400, detail="Invalid dimension_unit_override")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx/.xls files are accepted")

    file_bytes = await file.read()
    settings_row = await get_settings_row(db)

    try:
        parsed_rows = parse_workbook(
            file_bytes,
            weight_unit_override,
            dimension_unit_override,
            settings_row.default_service_code,
            app_settings.bulk_max_rows,
        )
    except HeaderMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not parsed_rows:
        raise HTTPException(status_code=400, detail="File has no data rows")

    run = BulkRun(
        created_at=datetime.datetime.now(datetime.timezone.utc),
        status="draft",
        source_filename=file.filename,
        source_path="",
        weight_unit_override=weight_unit_override,
        dimension_unit_override=dimension_unit_override,
        default_service_code=settings_row.default_service_code,
        total_rows=len(parsed_rows),
        valid_rows=sum(1 for r in parsed_rows if r.valid),
        success_count=0,
        failure_count=0,
    )
    db.add(run)
    await db.flush()

    source_path, _ = write_bytes_under_root(f"bulk/{run.id}", "upload.xlsx", file_bytes)
    run.source_path = source_path

    row_errors: list[BulkRowError] = []
    for parsed in parsed_rows:
        db.add(
            BulkRunRow(
                bulk_run_id=run.id,
                row_number=parsed.row_number,
                raw=parsed.raw,
                status="pending" if parsed.valid else "invalid",
                validation_error=parsed.error,
            )
        )
        if not parsed.valid:
            row_errors.append(BulkRowError(row_number=parsed.row_number, error=parsed.error))
            run.failure_count += 1

    await db.commit()
    await db.refresh(run)
    return BulkUploadResponse(run=run, row_errors=row_errors)


@router.post("/bulk/runs/{run_id}/start", response_model=BulkRunOut)
async def start_bulk_run(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(BulkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "draft":
        raise HTTPException(status_code=400, detail=f"Run is not in draft status (is '{run.status}')")
    run.status = "queued"
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/bulk/runs", response_model=list[BulkRunOut])
async def list_bulk_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BulkRun).order_by(BulkRun.created_at.desc()))
    return result.scalars().all()


@router.get("/bulk/runs/{run_id}", response_model=BulkRunOut)
async def get_bulk_run(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(BulkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


async def _run_rows(db: AsyncSession, run_id: int) -> list[BulkRunRow]:
    result = await db.execute(
        select(BulkRunRow).where(BulkRunRow.bulk_run_id == run_id).order_by(BulkRunRow.row_number)
    )
    return result.scalars().all()


@router.get("/bulk/runs/{run_id}/report.xlsx")
async def download_bulk_report(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(BulkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    rows = await _run_rows(db, run_id)

    label_ids = [r.label_id for r in rows if r.label_id]
    labels_by_id = {}
    if label_ids:
        result = await db.execute(select(Label).where(Label.id.in_(label_ids)))
        labels_by_id = {label.id: label for label in result.scalars().all()}

    content = build_report_xlsx(rows, labels_by_id)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=bulk_run_{run_id}_report.xlsx"},
    )


@router.get("/bulk/runs/{run_id}/labels.zip")
async def download_bulk_labels_zip(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(BulkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    result = await db.execute(
        select(Label).where(Label.bulk_run_id == run_id, Label.status == "created")
    )
    labels = result.scalars().all()
    content = build_labels_zip(labels)
    return StreamingResponse(
        iter([content]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=bulk_run_{run_id}_labels.zip"},
    )

"""Manifest Close (D25-D37, task doc "Plan — Manifest Close (2026-08-31)").

No `manifest_service.py` (D35): Close has exactly one caller, so the logic
lives directly in this router, the same way Void lives in `labels.py`.
"""

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.epg import client as epg_client
from app.epg import mapping as epg_mapping
from app.labels_service import get_settings_row, mirror_quota
from app.models import Label, ManifestClose
from app.schemas import ManifestCloseOut, ManifestCloseResolve, ManifestOpenSummary
from app.security import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


def _account_number_column(environment: str) -> str:
    return "epg_account_number_sandbox" if environment == "sandbox" else "epg_account_number_production"


async def _open_label_ids(db: AsyncSession, environment: str) -> list[int]:
    result = await db.execute(
        select(Label.id).where(
            Label.status == "created",
            Label.manifest_close_id.is_(None),
            Label.epg_environment == environment,
        )
    )
    return [row[0] for row in result.all()]


async def _pending_close(db: AsyncSession, environment: str) -> ManifestClose | None:
    result = await db.execute(
        select(ManifestClose)
        .where(ManifestClose.epg_environment == environment, ManifestClose.status == "pending")
        .order_by(ManifestClose.created_at.desc())
    )
    return result.scalars().first()


def _to_close_out(close: ManifestClose) -> ManifestCloseOut:
    candidate_ids = close.candidate_label_ids or []
    return ManifestCloseOut(
        id=close.id,
        created_at=close.created_at,
        finished_at=close.finished_at,
        status=close.status,
        epg_environment=close.epg_environment,
        account_number=close.account_number,
        close_id=close.close_id,
        close_reports=close.close_reports,
        candidate_label_ids=candidate_ids,
        error_message=close.error_message,
        resolved_manually=close.resolved_manually,
        label_count=len(candidate_ids),
    )


async def _attach_candidates(db: AsyncSession, close: ManifestClose) -> None:
    candidate_ids = close.candidate_label_ids or []
    if not candidate_ids:
        return
    await db.execute(
        update(Label)
        .where(Label.id.in_(candidate_ids), Label.manifest_close_id.is_(None))
        .values(manifest_close_id=close.id)
    )


@router.get("/manifest/open", response_model=ManifestOpenSummary)
async def get_open_summary(db: AsyncSession = Depends(get_db)):
    settings_row = await get_settings_row(db)
    environment = settings_row.epg_environment
    configured_account_number = getattr(settings_row, _account_number_column(environment))

    open_ids = await _open_label_ids(db, environment)
    pending = await _pending_close(db, environment)

    epg_account_number: str | None = None
    epg_package_count: int | None = None
    epg_error: str | None = None
    try:
        raw, quota = await epg_client.list_open(environment)
        await mirror_quota(db, settings_row, quota)
        await db.commit()
        packages = epg_mapping.parse_open_packages(raw)
        epg_package_count = sum(p["package_count"] for p in packages)
        if packages:
            epg_account_number = packages[0]["account_number"]
    except epg_client.EPGError as exc:
        epg_error = str(exc)

    return ManifestOpenSummary(
        environment=environment,
        configured_account_number=configured_account_number,
        open_count=len(open_ids),
        epg_account_number=epg_account_number,
        epg_package_count=epg_package_count,
        epg_checked_at=datetime.datetime.now(datetime.timezone.utc),
        epg_error=epg_error,
        pending_close=_to_close_out(pending) if pending else None,
    )


@router.post("/manifest/closes", response_model=ManifestCloseOut)
async def create_close(db: AsyncSession = Depends(get_db)):
    settings_row = await get_settings_row(db)
    environment = settings_row.epg_environment
    account_number = getattr(settings_row, _account_number_column(environment))

    if not account_number:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No EPG account number captured yet for {environment}. "
                "Ship or rate a label in this environment first — the account "
                "number is captured automatically from that response."
            ),
        )

    if await _pending_close(db, environment) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A close for {environment} is still pending resolution.",
        )

    candidate_ids = await _open_label_ids(db, environment)

    close = ManifestClose(
        created_at=datetime.datetime.now(datetime.timezone.utc),
        status="pending",
        epg_environment=environment,
        account_number=account_number,
        candidate_label_ids=candidate_ids,
        resolved_manually=False,
    )
    db.add(close)
    # Commit before calling EPG (D31/D30 precedent, same as create_label
    # inserting before spending): a crash mid-call still leaves a trace.
    await db.commit()
    await db.refresh(close)

    try:
        response, quota = await epg_client.close_manifest(environment, account_number)
    except epg_client.EPGTimeoutError as exc:
        close.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail=f"EPG close timed out; close #{close.id} needs checking, labels are still open.",
        )
    except epg_client.EPGError as exc:
        close.status = "failed"
        close.finished_at = datetime.datetime.now(datetime.timezone.utc)
        close.error_message = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"EPG close failed: {exc}")

    await mirror_quota(db, settings_row, quota)
    close.epg_response_json = epg_mapping.truncate_long_strings(response)

    if not epg_mapping.is_success(response):
        _, message = epg_mapping.extract_error(response)
        close.status = "failed"
        close.finished_at = datetime.datetime.now(datetime.timezone.utc)
        close.error_message = message
        await db.commit()
        raise HTTPException(status_code=502, detail=f"EPG close failed: {message}")

    close.status = "completed"
    close.finished_at = datetime.datetime.now(datetime.timezone.utc)
    close.close_id = epg_mapping.extract_close_id(response)
    close.close_reports = epg_mapping.extract_close_reports(response)
    await _attach_candidates(db, close)

    await db.commit()
    await db.refresh(close)
    return _to_close_out(close)


@router.post("/manifest/closes/{close_id}/resolve", response_model=ManifestCloseOut)
async def resolve_close(close_id: int, payload: ManifestCloseResolve, db: AsyncSession = Depends(get_db)):
    close = await db.get(ManifestClose, close_id)
    if not close:
        raise HTTPException(status_code=404, detail="Close not found")
    if close.status != "pending":
        raise HTTPException(status_code=400, detail=f"Close is already '{close.status}'; nothing to resolve")

    close.resolved_manually = True
    close.finished_at = datetime.datetime.now(datetime.timezone.utc)

    if payload.outcome == "completed":
        close.status = "completed"
        await _attach_candidates(db, close)
    else:
        close.status = "failed"

    await db.commit()
    await db.refresh(close)
    return _to_close_out(close)


@router.get("/manifest/closes", response_model=list[ManifestCloseOut])
async def list_closes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ManifestClose).order_by(ManifestClose.created_at.desc()))
    return [_to_close_out(close) for close in result.scalars().all()]


@router.get("/manifest/closes/{close_id}", response_model=ManifestCloseOut)
async def get_close(close_id: int, db: AsyncSession = Depends(get_db)):
    close = await db.get(ManifestClose, close_id)
    if not close:
        raise HTTPException(status_code=404, detail="Close not found")
    return _to_close_out(close)

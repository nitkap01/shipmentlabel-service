"""The bulk-run poller (D7, D8).

A single in-process asyncio task claims one queued run at a time with
`SELECT ... FOR UPDATE SKIP LOCKED`, then processes its rows sequentially.
Every row's outcome is committed immediately, so a crash/restart resumes
only rows still `pending` — a row that already succeeded is never re-sent,
and a row's EPG call is never auto-retried.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.bulk.parse import validate_raw_row
from app.db import SessionLocal
from app.epg.client import EPGNotConfiguredError
from app.labels_service import create_label, get_settings_row
from app.models import BulkRun, BulkRunRow

SEQUENTIAL_DELAY_SECONDS = 0.5
QUOTA_EXHAUSTED_STATUS = "403"
POLL_INTERVAL_SECONDS = 2.0


async def claim_next_run(db: AsyncSession) -> BulkRun | None:
    result = await db.execute(
        text(
            "SELECT id FROM bulk_runs WHERE status = 'queued' "
            "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
    )
    row = result.first()
    if row is None:
        return None

    run = await db.get(BulkRun, row[0])
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    await db.commit()
    return run


async def process_run(db: AsyncSession, run: BulkRun) -> None:
    settings_row = await get_settings_row(db)

    pending_rows = (
        await db.execute(
            select(BulkRunRow)
            .where(BulkRunRow.bulk_run_id == run.id, BulkRunRow.status == "pending")
            .order_by(BulkRunRow.row_number)
        )
    ).scalars().all()

    quota_exhausted = False

    for row in pending_rows:
        if quota_exhausted:
            row.status = "skipped"
            row.processed_at = datetime.now(timezone.utc)
            await db.commit()
            continue

        parsed = validate_raw_row(
            row.row_number,
            row.raw,
            run.weight_unit_override,
            run.dimension_unit_override,
            run.default_service_code,
        )
        if not parsed.valid:
            row.status = "invalid"
            row.validation_error = parsed.error
            row.processed_at = datetime.now(timezone.utc)
            run.failure_count += 1
            await db.commit()
            continue

        try:
            label = await create_label(
                db,
                fields=parsed.label_fields,
                source="bulk",
                bulk_run_id=run.id,
                settings_row=settings_row,
            )
        except EPGNotConfiguredError as exc:
            run.status = "failed"
            run.error_message = str(exc)
            await db.commit()
            return

        row.processed_at = datetime.now(timezone.utc)
        if label.status == "created":
            row.status = "success"
            row.label_id = label.id
            run.success_count += 1
        else:
            row.status = "failed"
            row.epg_error_code = label.epg_error_code
            row.epg_error_message = label.epg_error_message
            run.failure_count += 1
            if label.epg_error_code == QUOTA_EXHAUSTED_STATUS:
                quota_exhausted = True
                run.error_message = "EPG quota exhausted mid-run; remaining rows skipped."

        await db.commit()
        await asyncio.sleep(SEQUENTIAL_DELAY_SECONDS)

    run.status = "completed" if run.failure_count == 0 else "completed_with_errors"
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()


async def poll_forever(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        async with SessionLocal() as db:
            run = await claim_next_run(db)
            if run is not None:
                await process_run(db, run)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

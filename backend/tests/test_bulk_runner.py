from datetime import datetime, timezone

from sqlalchemy import select

from app.bulk.runner import claim_next_run, process_run
from app.db import SessionLocal
from app.epg.client import EPGError, EPGTimeoutError
from app.models import BulkRun, BulkRunRow, Label
from app.storage import resolve_under_root
from tests.conftest import make_ship_failure, make_ship_success


def _row_raw(name: str, ref: str) -> dict:
    return {
        "Recipient Name": name,
        "Recipient Company": None,
        "Address Line 1": "123 Main St",
        "Address Line 2": None,
        "City": "Newark",
        "State": "NJ",
        "Postal Code": "07102",
        "Phone": None,
        "Email": None,
        "Weight": 4,
        "Weight Unit": "oz",
        "Length": None,
        "Width": None,
        "Height": None,
        "Dimension Unit": None,
        "Declared Value": 10.00,
        "Reference / Order #": ref,
        "Service Code": None,
    }


async def _make_queued_run(db, n_rows: int) -> BulkRun:
    run = BulkRun(
        created_at=datetime.now(timezone.utc),
        status="queued",
        source_filename="test.xlsx",
        source_path="bulk/test/upload.xlsx",
        weight_unit_override=None,
        dimension_unit_override=None,
        default_service_code="EP05",
        total_rows=n_rows,
        valid_rows=n_rows,
        success_count=0,
        failure_count=0,
    )
    db.add(run)
    await db.flush()
    for i in range(1, n_rows + 1):
        db.add(
            BulkRunRow(
                bulk_run_id=run.id,
                row_number=i,
                raw=_row_raw(f"Recipient {i}", f"REF{i}"),
                status="pending",
            )
        )
    await db.commit()
    await db.refresh(run)
    return run


async def test_partial_failures_produce_completed_with_errors(monkeypatch, fake_png_base64):
    calls = {"n": 0}

    async def fake_ship(environment, body):
        calls["n"] += 1
        if calls["n"] in (2, 4):
            return make_ship_failure()
        return make_ship_success(fake_png_base64, tracking=f"T{calls['n']}", unique_ref=f"U{calls['n']}")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    monkeypatch.setattr("app.bulk.runner.SEQUENTIAL_DELAY_SECONDS", 0)

    async with SessionLocal() as db:
        await _make_queued_run(db, 5)
        run = await claim_next_run(db)
        await process_run(db, run)
        await db.refresh(run)

        assert run.status == "completed_with_errors"
        assert run.success_count == 3
        assert run.failure_count == 2

        rows = (
            await db.execute(
                select(BulkRunRow).where(BulkRunRow.bulk_run_id == run.id).order_by(BulkRunRow.row_number)
            )
        ).scalars().all()
        assert [r.status for r in rows] == ["success", "failed", "success", "failed", "success"]

        labels = (await db.execute(select(Label).where(Label.bulk_run_id == run.id))).scalars().all()
        assert len(labels) == 5  # every row gets a labels row, even ones that failed at EPG (audit trail)
        created_labels = [label for label in labels if label.status == "created"]
        assert len(created_labels) == 3
        for label in created_labels:
            assert label.pdf_path
            assert resolve_under_root(label.pdf_path).exists()


async def test_restart_resume_does_not_resend_already_successful_rows(monkeypatch, fake_png_base64):
    calls = []

    async def fake_ship(environment, body):
        calls.append(body["referenceId"])
        return make_ship_success(fake_png_base64, tracking=f"T{len(calls)}", unique_ref=f"U{len(calls)}")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    monkeypatch.setattr("app.bulk.runner.SEQUENTIAL_DELAY_SECONDS", 0)

    async with SessionLocal() as db:
        await _make_queued_run(db, 3)
        run = await claim_next_run(db)

        rows = (
            await db.execute(select(BulkRunRow).where(BulkRunRow.bulk_run_id == run.id))
        ).scalars().all()
        rows[0].status = "success"  # simulate: a prior crashed run already succeeded on row 1
        await db.commit()

        await process_run(db, run)

        assert len(calls) == 2  # only rows 2 and 3 were ever sent to EPG


async def test_quota_exhaustion_stops_run_and_skips_remaining_rows(monkeypatch, fake_png_base64):
    calls = {"n": 0}

    async def fake_ship(environment, body):
        calls["n"] += 1
        if calls["n"] == 2:
            raise EPGError("quota exceeded", status_code=403)
        return make_ship_success(fake_png_base64, tracking=f"T{calls['n']}", unique_ref=f"U{calls['n']}")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    monkeypatch.setattr("app.bulk.runner.SEQUENTIAL_DELAY_SECONDS", 0)

    async with SessionLocal() as db:
        await _make_queued_run(db, 4)
        run = await claim_next_run(db)
        await process_run(db, run)
        await db.refresh(run)

        rows = (
            await db.execute(
                select(BulkRunRow).where(BulkRunRow.bulk_run_id == run.id).order_by(BulkRunRow.row_number)
            )
        ).scalars().all()
        assert [r.status for r in rows] == ["success", "failed", "skipped", "skipped"]
        assert run.error_message and "quota" in run.error_message.lower()


async def test_timeout_leaves_label_pending_and_row_marked_failed_not_retried(monkeypatch):
    async def fake_ship(environment, body):
        raise EPGTimeoutError("connection timed out")

    monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship)
    monkeypatch.setattr("app.bulk.runner.SEQUENTIAL_DELAY_SECONDS", 0)

    async with SessionLocal() as db:
        await _make_queued_run(db, 1)
        run = await claim_next_run(db)
        await process_run(db, run)

        labels = (await db.execute(select(Label).where(Label.bulk_run_id == run.id))).scalars().all()
        assert len(labels) == 1
        assert labels[0].status == "pending"  # ambiguous outcome, never marked failed (D8)

        rows = (await db.execute(select(BulkRunRow).where(BulkRunRow.bulk_run_id == run.id))).scalars().all()
        assert rows[0].status == "failed"  # not left `pending` at the row level, so it is never resent

        # Resuming again must not re-send this row.
        run.status = "queued"
        await db.commit()
        calls = {"n": 0}

        async def fake_ship_again(environment, body):
            calls["n"] += 1
            raise EPGTimeoutError("should not be called")

        monkeypatch.setattr("app.labels_service.epg_client.ship", fake_ship_again)
        run2 = await claim_next_run(db)
        await process_run(db, run2)
        assert calls["n"] == 0

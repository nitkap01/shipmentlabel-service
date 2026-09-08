import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Computed, DateTime, ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Every timestamptz column in migrations/001_initial.sql must round-trip as
    # a timezone-aware Python datetime — asyncpg rejects an aware value bound
    # against a naive TIMESTAMP, which SQLAlchemy otherwise infers by default.
    type_annotation_map = {datetime.datetime: DateTime(timezone=True)}


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)

    from_name: Mapped[str]
    from_company: Mapped[str]
    from_address1: Mapped[str]
    from_address2: Mapped[str | None]
    from_city: Mapped[str]
    from_state: Mapped[str]
    from_postal_code: Mapped[str]
    from_country: Mapped[str]
    from_phone: Mapped[str | None]
    from_email: Mapped[str | None]

    label_directory: Mapped[str]
    default_service_code: Mapped[str]
    epg_environment: Mapped[str]

    epg_account_number_sandbox: Mapped[str | None]
    epg_account_number_production: Mapped[str | None]

    last_quota_available: Mapped[int | None]
    last_quota_checked_at: Mapped[datetime.datetime | None]

    updated_at: Mapped[datetime.datetime]


class BulkRun(Base):
    __tablename__ = "bulk_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime.datetime]
    started_at: Mapped[datetime.datetime | None]
    finished_at: Mapped[datetime.datetime | None]

    status: Mapped[str]
    source_filename: Mapped[str]
    source_path: Mapped[str]

    weight_unit_override: Mapped[str | None]
    dimension_unit_override: Mapped[str | None]
    default_service_code: Mapped[str]

    total_rows: Mapped[int]
    valid_rows: Mapped[int]
    success_count: Mapped[int]
    failure_count: Mapped[int]

    error_message: Mapped[str | None]


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime.datetime]

    status: Mapped[str]
    source: Mapped[str]
    bulk_run_id: Mapped[int | None] = mapped_column(ForeignKey("bulk_runs.id"))
    manifest_close_id: Mapped[int | None] = mapped_column(ForeignKey("manifest_closes.id"))
    epg_environment: Mapped[str]

    service_code: Mapped[str]

    recipient_name: Mapped[str]
    recipient_company: Mapped[str | None]
    recipient_address1: Mapped[str]
    recipient_address2: Mapped[str | None]
    recipient_city: Mapped[str]
    recipient_state: Mapped[str]
    recipient_postal_code: Mapped[str]
    recipient_country: Mapped[str]
    recipient_phone: Mapped[str | None]
    recipient_phone_digits: Mapped[str | None]
    recipient_email: Mapped[str | None]

    from_name: Mapped[str | None]
    from_company: Mapped[str]
    from_address1: Mapped[str]
    from_address2: Mapped[str | None]
    from_city: Mapped[str]
    from_state: Mapped[str]
    from_postal_code: Mapped[str]
    from_country: Mapped[str]
    from_phone: Mapped[str | None]
    from_email: Mapped[str | None]

    weight_value: Mapped[Decimal]
    weight_unit: Mapped[str]
    weight_oz: Mapped[Decimal]

    length_value: Mapped[Decimal | None]
    width_value: Mapped[Decimal | None]
    height_value: Mapped[Decimal | None]
    dimension_unit: Mapped[str | None]
    length_in: Mapped[Decimal | None]
    width_in: Mapped[Decimal | None]
    height_in: Mapped[Decimal | None]

    declared_value: Mapped[Decimal]
    currency_code: Mapped[str]
    reference1: Mapped[str | None]
    notes: Mapped[str | None]

    tracking_number: Mapped[str | None]
    unique_reference_id: Mapped[str | None]

    epg_request_json: Mapped[dict | None] = mapped_column(JSONB)
    epg_response_json: Mapped[dict | None] = mapped_column(JSONB)
    epg_error_code: Mapped[str | None]
    epg_error_message: Mapped[str | None]

    pdf_path: Mapped[str | None]
    pdf_size_bytes: Mapped[int | None]

    voided_at: Mapped[datetime.datetime | None]
    void_error: Mapped[str | None]

    # Real expression lives in migrations/001_initial.sql, redefined by
    # migrations/004_search_includes_tracking.sql (GENERATED ALWAYS AS ... STORED).
    # Computed() here only tells SQLAlchemy to never include this column in INSERT/UPDATE.
    search_text: Mapped[str | None] = mapped_column(Computed("NULL"), nullable=True)


class BulkRunRow(Base):
    __tablename__ = "bulk_run_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bulk_run_id: Mapped[int] = mapped_column(ForeignKey("bulk_runs.id"))
    row_number: Mapped[int]

    raw: Mapped[dict] = mapped_column(JSONB)

    status: Mapped[str]
    validation_error: Mapped[str | None]
    epg_error_code: Mapped[str | None]
    epg_error_message: Mapped[str | None]

    label_id: Mapped[int | None] = mapped_column(ForeignKey("labels.id"))
    processed_at: Mapped[datetime.datetime | None]


class ManifestClose(Base):
    __tablename__ = "manifest_closes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime.datetime]
    finished_at: Mapped[datetime.datetime | None]

    status: Mapped[str]
    epg_environment: Mapped[str]
    account_number: Mapped[str]

    close_id: Mapped[str | None]
    # Shape unknown (F6 — the vendor doc gives no sample POST /Ship/Close
    # response). Stored as-is, whatever it turns out to be.
    close_reports: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    candidate_label_ids: Mapped[list] = mapped_column(JSONB)
    epg_response_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None]
    resolved_manually: Mapped[bool]

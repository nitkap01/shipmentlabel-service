import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str


class FromAddressOverride(BaseModel):
    name: str | None = None
    company: str
    address1: str
    address2: str | None = None
    city: str
    state: str
    postal_code: str
    phone: str | None = None
    email: str | None = None


class LabelCreateRequest(BaseModel):
    recipient_name: str
    recipient_company: str | None = None
    recipient_address1: str
    recipient_address2: str | None = None
    recipient_city: str
    recipient_state: str
    recipient_postal_code: str
    recipient_phone: str | None = None
    recipient_email: str | None = None

    weight_value: Decimal
    weight_unit: str

    length_value: Decimal | None = None
    width_value: Decimal | None = None
    height_value: Decimal | None = None
    dimension_unit: str | None = None

    declared_value: Decimal
    reference1: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)

    service_code: str | None = None
    from_override: FromAddressOverride | None = None


class LabelBulkDownloadRequest(BaseModel):
    label_ids: list[int]


class LabelOut(BaseModel):
    id: int
    created_at: datetime.datetime
    status: str
    source: str
    bulk_run_id: int | None
    service_code: str

    recipient_name: str
    recipient_company: str | None
    recipient_address1: str
    recipient_address2: str | None
    recipient_city: str
    recipient_state: str
    recipient_postal_code: str
    recipient_country: str
    recipient_phone: str | None
    recipient_email: str | None

    weight_value: Decimal
    weight_unit: str
    weight_oz: Decimal
    length_value: Decimal | None
    width_value: Decimal | None
    height_value: Decimal | None
    dimension_unit: str | None

    declared_value: Decimal
    currency_code: str
    reference1: str | None
    notes: str | None

    tracking_number: str | None
    unique_reference_id: str | None
    epg_error_code: str | None
    epg_error_message: str | None

    pdf_path: str | None
    voided_at: datetime.datetime | None
    void_error: str | None
    manifest_close_id: int | None

    model_config = {"from_attributes": True}


class LabelListResponse(BaseModel):
    items: list[LabelOut]
    total: int
    page: int
    page_size: int


class LabelStats(BaseModel):
    total: int
    this_month: int
    voided: int
    needs_checking: int


class SettingsOut(BaseModel):
    from_name: str
    from_company: str
    from_address1: str
    from_address2: str | None
    from_city: str
    from_state: str
    from_postal_code: str
    from_country: str
    from_phone: str | None
    from_email: str | None

    label_directory: str
    default_service_code: str
    epg_environment: str
    available_environments: list[str]

    last_quota_available: int | None
    last_quota_checked_at: datetime.datetime | None

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    from_name: str
    from_company: str
    from_address1: str
    from_address2: str | None = None
    from_city: str
    from_state: str
    from_postal_code: str
    from_phone: str | None = None
    from_email: str | None = None

    label_directory: str
    default_service_code: str
    epg_environment: str


class DirectoryEntry(BaseModel):
    name: str
    path: str


class DirectoryListing(BaseModel):
    path: str
    entries: list[DirectoryEntry]


class DirectoryCreate(BaseModel):
    path: str = ""
    name: str


class BulkRunOut(BaseModel):
    id: int
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None
    status: str
    source_filename: str
    total_rows: int
    valid_rows: int
    success_count: int
    failure_count: int
    error_message: str | None

    model_config = {"from_attributes": True}


class BulkRowError(BaseModel):
    row_number: int
    error: str


class BulkUploadResponse(BaseModel):
    run: BulkRunOut
    row_errors: list[BulkRowError]


class ManifestCloseOut(BaseModel):
    id: int
    created_at: datetime.datetime
    finished_at: datetime.datetime | None
    status: str
    epg_environment: str
    account_number: str
    close_id: str | None
    close_reports: Any | None
    candidate_label_ids: list[int]
    error_message: str | None
    resolved_manually: bool
    label_count: int

    model_config = {"from_attributes": True}


class ManifestOpenSummary(BaseModel):
    environment: str
    configured_account_number: str | None
    open_count: int
    epg_account_number: str | None
    epg_package_count: int | None
    epg_checked_at: datetime.datetime
    epg_error: str | None
    pending_close: ManifestCloseOut | None


class ManifestCloseResolve(BaseModel):
    outcome: Literal["completed", "failed"]

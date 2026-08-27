"""Bulk run report (.xlsx) and label zip — generated on demand (D18), never stored."""

import io
import zipfile

from openpyxl import Workbook

from app.bulk.template import TEMPLATE_HEADERS
from app.storage import resolve_under_root


def build_report_xlsx(rows: list, labels_by_id: dict) -> bytes:
    wb = Workbook()

    all_sheet = wb.active
    all_sheet.title = "All Rows"
    all_sheet.append(["Row", "Status", "Error", *TEMPLATE_HEADERS])
    for row in rows:
        label = labels_by_id.get(row.label_id)
        error = row.validation_error or row.epg_error_message or ""
        all_sheet.append(
            [row.row_number, row.status, error, *[row.raw.get(h) for h in TEMPLATE_HEADERS]]
        )

    failed_sheet = wb.create_sheet("Failed Rows")
    failed_sheet.append(TEMPLATE_HEADERS)
    for row in rows:
        if row.status in ("failed", "invalid"):
            failed_sheet.append([row.raw.get(h) for h in TEMPLATE_HEADERS])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def build_labels_zip(labels: list) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for label in labels:
            if not label.pdf_path:
                continue
            path = resolve_under_root(label.pdf_path)
            if path.exists():
                zf.write(path, arcname=path.name)
    return out.getvalue()

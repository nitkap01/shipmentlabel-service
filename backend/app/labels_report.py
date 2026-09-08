"""Label-wise report (.xlsx) for a date range — generated on demand, never stored."""

import io

from openpyxl import Workbook

REPORT_HEADERS = [
    "Label ID",
    "Created",
    "Status",
    "Environment",
    "Service Code",
    "Tracking Number",
    "Recipient",
    "Company",
    "Address",
    "City",
    "State",
    "Postal Code",
    "Weight",
    "Declared Value",
    "Reference",
    "Notes",
    "Source",
    "Bulk Run",
    "Manifest Close",
    "Voided At",
    "Error",
]


def build_labels_report_xlsx(labels: list, timezone) -> bytes:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Labels"
    sheet.append(REPORT_HEADERS)

    for label in labels:
        created = label.created_at.astimezone(timezone).strftime("%Y-%m-%d %H:%M:%S") if label.created_at else ""
        voided = label.voided_at.astimezone(timezone).strftime("%Y-%m-%d %H:%M:%S") if label.voided_at else ""
        sheet.append(
            [
                label.id,
                created,
                label.status,
                label.epg_environment,
                label.service_code,
                label.tracking_number or "",
                label.recipient_name,
                label.recipient_company or "",
                label.recipient_address1,
                label.recipient_city,
                label.recipient_state,
                label.recipient_postal_code,
                f"{label.weight_value} {label.weight_unit}",
                float(label.declared_value),
                label.reference1 or "",
                label.notes or "",
                label.source,
                label.bulk_run_id or "",
                label.manifest_close_id or "",
                voided,
                label.epg_error_message or label.void_error or "",
            ]
        )

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

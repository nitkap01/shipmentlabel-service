"""The locked bulk-upload Excel template (D20). 18 columns, fixed order."""

import io

from openpyxl import Workbook

TEMPLATE_HEADERS = [
    "Recipient Name",
    "Recipient Company",
    "Address Line 1",
    "Address Line 2",
    "City",
    "State",
    "Postal Code",
    "Phone",
    "Email",
    "Weight",
    "Weight Unit",
    "Length",
    "Width",
    "Height",
    "Dimension Unit",
    "Declared Value",
    "Reference / Order #",
    "Service Code",
]


def generate_blank_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Labels"
    ws.append(TEMPLATE_HEADERS)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def normalize_header(header: str | None) -> str:
    return (header or "").strip().lower()


NORMALIZED_HEADERS = [normalize_header(h) for h in TEMPLATE_HEADERS]

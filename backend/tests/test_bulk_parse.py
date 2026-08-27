import io

import pytest
from openpyxl import Workbook

from app.bulk.parse import HeaderMismatchError, parse_workbook
from app.bulk.template import TEMPLATE_HEADERS


def _workbook_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(TEMPLATE_HEADERS)
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _valid_row(**overrides) -> list:
    base = {
        "Recipient Name": "Jane Doe",
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
        "Reference / Order #": "REF1",
        "Service Code": None,
    }
    base.update(overrides)
    return [base[h] for h in TEMPLATE_HEADERS]


def test_missing_and_unknown_headers_reject_whole_file():
    wb = Workbook()
    ws = wb.active
    ws.append(["Recipient Name", "Some Unknown Column"])
    ws.append(["Jane Doe", "x"])
    out = io.BytesIO()
    wb.save(out)

    with pytest.raises(HeaderMismatchError) as exc_info:
        parse_workbook(out.getvalue(), None, None, "EP05", 500)

    assert "Address Line 1" in str(exc_info.value)
    assert "Some Unknown Column" in str(exc_info.value)


def test_valid_row_parses_with_no_overrides():
    content = _workbook_bytes([_valid_row()])
    rows = parse_workbook(content, None, None, "EP05", 500)
    assert len(rows) == 1
    assert rows[0].valid
    assert rows[0].label_fields["weight_unit"] == "oz"
    assert rows[0].label_fields["service_code"] == "EP05"


@pytest.mark.parametrize(
    "missing_field",
    ["Recipient Name", "Address Line 1", "City", "Postal Code"],
)
def test_missing_required_field_marks_row_invalid(missing_field):
    content = _workbook_bytes([_valid_row(**{missing_field: None})])
    rows = parse_workbook(content, None, None, "EP05", 500)
    assert not rows[0].valid
    assert rows[0].error


def test_batch_weight_override_wins_over_row_column():
    content = _workbook_bytes([_valid_row(**{"Weight Unit": "lb"})])
    rows = parse_workbook(content, "kg", None, "EP05", 500)
    assert rows[0].valid
    assert rows[0].label_fields["weight_unit"] == "kg"


def test_batch_dimension_override_wins_over_row_column_independently_of_weight():
    content = _workbook_bytes(
        [_valid_row(Length=10, Width=5, Height=3, **{"Dimension Unit": "cm"})]
    )
    rows = parse_workbook(content, None, "inch", "EP05", 500)
    assert rows[0].valid
    assert rows[0].label_fields["dimension_unit"] == "inch"
    assert rows[0].label_fields["weight_unit"] == "oz"  # untouched by the dimension override


def test_missing_weight_unit_and_no_override_is_invalid():
    content = _workbook_bytes([_valid_row(**{"Weight Unit": None})])
    rows = parse_workbook(content, None, None, "EP05", 500)
    assert not rows[0].valid


def test_partial_dimensions_invalid():
    content = _workbook_bytes([_valid_row(Length=10, Width=5, Height=None, **{"Dimension Unit": "inch"})])
    rows = parse_workbook(content, None, None, "EP05", 500)
    assert not rows[0].valid


def test_blank_service_code_uses_run_default():
    content = _workbook_bytes([_valid_row(**{"Service Code": None})])
    rows = parse_workbook(content, None, None, "EP03", 500)
    assert rows[0].label_fields["service_code"] == "EP03"


def test_invalid_service_code_marks_row_invalid():
    content = _workbook_bytes([_valid_row(**{"Service Code": "XX99"})])
    rows = parse_workbook(content, None, None, "EP05", 500)
    assert not rows[0].valid


def test_bad_state_code_rejected():
    content = _workbook_bytes([_valid_row(State="ZZ")])
    rows = parse_workbook(content, None, None, "EP05", 500)
    assert not rows[0].valid


def test_bad_postal_code_rejected():
    content = _workbook_bytes([_valid_row(**{"Postal Code": "abc"})])
    rows = parse_workbook(content, None, None, "EP05", 500)
    assert not rows[0].valid


def test_row_cap_enforced():
    content = _workbook_bytes([_valid_row() for _ in range(5)])
    rows = parse_workbook(content, None, None, "EP05", 3)
    assert len(rows) == 5
    assert all(not r.valid for r in rows[3:])
    assert all(r.valid for r in rows[:3])

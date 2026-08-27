from decimal import Decimal

import pytest

from app.units import UnitError, to_inches, to_ounces


def test_oz_passthrough():
    assert to_ounces(Decimal("16"), "oz") == Decimal("16.00")


def test_lb_to_oz():
    assert to_ounces(Decimal("1"), "lb") == Decimal("16.00")


def test_kg_to_oz_rounds_up():
    # 1kg = 35.27396195 oz -> rounds up to 35.28
    assert to_ounces(Decimal("1"), "kg") == Decimal("35.28")


def test_inch_passthrough():
    assert to_inches(Decimal("10"), "inch") == Decimal("10.00")


def test_cm_to_inch_rounds_up():
    # 10cm = 3.93700787in -> rounds up to 3.94
    assert to_inches(Decimal("10"), "cm") == Decimal("3.94")


def test_never_rounds_down():
    # 1oz in kg-equivalent check: ensure rounding never goes below the true value
    converted = to_ounces(Decimal("2"), "kg")
    assert converted >= Decimal("2") * Decimal("35.27396195")


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-1")])
def test_zero_or_negative_weight_rejected(value):
    with pytest.raises(UnitError):
        to_ounces(value, "oz")


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-5")])
def test_zero_or_negative_dimension_rejected(value):
    with pytest.raises(UnitError):
        to_inches(value, "inch")


def test_unknown_weight_unit_rejected():
    with pytest.raises(UnitError):
        to_ounces(Decimal("1"), "stone")


def test_unknown_dimension_unit_rejected():
    with pytest.raises(UnitError):
        to_inches(Decimal("1"), "furlong")

"""Unit conversion for EPG requests.

Confirmed empirically against the EPG sandbox on 2026-08-27 (see the task
doc's "Phase 0 findings"): weight must be in OUNCES and dimensions in
INCHES. Always round UP so a shipment is never under-declared.
"""

from decimal import ROUND_UP, Decimal

OZ_PER_KG = Decimal("35.27396195")
OZ_PER_LB = Decimal("16")
IN_PER_CM = Decimal("0.393700787")

WEIGHT_UNITS = {"oz", "kg", "lb"}
DIMENSION_UNITS = {"inch", "cm"}


class UnitError(ValueError):
    pass


def _round_up(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_UP)


def to_ounces(value: Decimal, unit: str) -> Decimal:
    if unit not in WEIGHT_UNITS:
        raise UnitError(f"Unknown weight unit: {unit!r}")
    if value <= 0:
        raise UnitError("Weight must be greater than zero")

    if unit == "oz":
        converted = value
    elif unit == "lb":
        converted = value * OZ_PER_LB
    else:  # kg
        converted = value * OZ_PER_KG
    return _round_up(converted)


def to_inches(value: Decimal, unit: str) -> Decimal:
    if unit not in DIMENSION_UNITS:
        raise UnitError(f"Unknown dimension unit: {unit!r}")
    if value <= 0:
        raise UnitError("Dimension must be greater than zero")

    converted = value if unit == "inch" else value * IN_PER_CM
    return _round_up(converted)

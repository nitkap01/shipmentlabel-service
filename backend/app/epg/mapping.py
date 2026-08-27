"""Build EPG /ship (and /rate) request bodies, and parse their responses.

Field names and required-ness come from documents/ePost API document.pdf.
The `customs` block's *actual* requirement (even for pure domestic
shipments) was discovered empirically on 2026-08-27 — see the task doc's
Phase 0 findings. It is intentionally not user-facing: Nitin never asked
for customs data entry, and this project is domestic-only, so we synthesize
a minimal, fixed customs block from data we already have on every shipment.
"""

import base64
from decimal import Decimal

FIXED_HS_CODE = "000000"
FIXED_ORIGIN_COUNTRY = "US"


class EPGResponseError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


def _combine_from_company(from_name: str | None, from_company: str) -> str:
    if from_name:
        return f"{from_name} / {from_company}"
    return from_company


def build_customs_block(declared_value: Decimal, recipient_name: str) -> dict:
    return {
        "description": "Merchandise",
        "items": [
            {
                "quantity": "1",
                "code": "ITEM1",
                "name": f"Merchandise for {recipient_name}"[:50],
                "value": str(declared_value),
                "hsCode": FIXED_HS_CODE,
                "originManufactureCountry": FIXED_ORIGIN_COUNTRY,
            }
        ],
    }


def build_ship_request(label: dict) -> dict:
    """`label` carries already-converted values: weight_oz, length_in/width_in/height_in."""
    package: dict = {
        "currencyCode": label["currency_code"],
        "value": str(label["declared_value"]),
        "weight": str(label["weight_oz"]),
        "customs": build_customs_block(label["declared_value"], label["recipient_name"]),
    }
    if label.get("reference1"):
        package["reference1"] = label["reference1"]
    if label.get("length_in") and label.get("width_in") and label.get("height_in"):
        package["dimensions"] = {
            "length": str(label["length_in"]),
            "width": str(label["width_in"]),
            "height": str(label["height_in"]),
        }

    body = {
        "serviceCode": label["service_code"],
        "referenceId": label["epg_reference_id"],
        "labelFormat": "PNG",
        "recipient": {
            "name": label["recipient_name"],
            "company": label.get("recipient_company") or None,
            "address1": label["recipient_address1"],
            "address2": label.get("recipient_address2") or None,
            "city": label["recipient_city"],
            "postalCode": label["recipient_postal_code"],
            "stateOrProvince": label["recipient_state"],
            "countryCode": label.get("recipient_country", "US"),
            "phone": label.get("recipient_phone") or None,
            "email": label.get("recipient_email") or None,
        },
        "from": {
            "company": _combine_from_company(label.get("from_name"), label["from_company"]),
            "address1": label["from_address1"],
            "address2": label.get("from_address2") or None,
            "city": label["from_city"],
            "postalCode": label["from_postal_code"],
            "stateOrProvince": label["from_state"],
            "countryCode": label.get("from_country", "US"),
            "phone": label.get("from_phone") or None,
            "email": label.get("from_email") or None,
        },
        "package": package,
    }
    return body


def is_success(response: dict) -> bool:
    return bool(response.get("wasSuccessful"))


def extract_error(response: dict) -> tuple[str | None, str]:
    errors = response.get("errors") or response.get("rateErrors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        message = first.get("message") if isinstance(first, dict) else str(first)
        return None, message or "EPG returned an error"
    return None, response.get("responseMessage") or "EPG returned an unspecified error"


def extract_label_png(response: dict) -> bytes:
    package = response.get("package") or {}
    labels = package.get("labels")
    if not labels or not isinstance(labels, list):
        raise EPGResponseError("No 'package.labels' array in EPG response")
    return base64.b64decode(labels[0])


def extract_tracking_number(response: dict) -> str | None:
    return (response.get("package") or {}).get("trackingNumber")


def extract_unique_reference_id(response: dict) -> str | None:
    return (response.get("package") or {}).get("uniqueReferenceId")


def strip_image_payload(response: dict) -> dict:
    """Copy of the response with label image bytes removed (D13) — safe to store in jsonb."""
    import copy

    stripped = copy.deepcopy(response)
    package = stripped.get("package")
    if isinstance(package, dict) and "labels" in package:
        package["labels"] = [f"<stripped, {len(v)} base64 chars>" for v in package["labels"]]
    return stripped


def strip_auth_header(request_body: dict) -> dict:
    """No-op placeholder: the auth header is never part of the JSON body, only headers.
    Kept as the single place D13's "strip credentials before storing" rule lives, in
    case a future EPG field structure ever needs a redaction pass.
    """
    return request_body

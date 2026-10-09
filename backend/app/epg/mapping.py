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


def void_result(reply) -> tuple[bool, str]:
    """SHIP-5: did ePost confirm the void? Sandbox (09_10_2026): HTTP 200 with a list of
    `{"package": {...}, "success": true, "secondaryMessage": ...}`; anything else is NOT a confirmed void."""
    items = reply if isinstance(reply, list) else [reply] if isinstance(reply, dict) else []
    if items and all(isinstance(i, dict) and i.get("success") is True for i in items):
        return True, ""
    for i in items:
        if isinstance(i, dict) and (i.get("secondaryMessage") or i.get("message")):
            return False, str(i.get("secondaryMessage") or i.get("message"))
    return False, "ePost's reply did not confirm the void"


def extract_error(response: dict) -> tuple[str | None, str]:
    errors = response.get("errors") or response.get("rateErrors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        message = first.get("message") if isinstance(first, dict) else str(first)
        return None, message or "EPG returned an error"
    return None, response.get("responseMessage") or "EPG returned an unspecified error"


def is_ambiguous_close_response(response: dict) -> bool:
    """A close call that got a non-error HTTP status back but an empty or
    non-JSON body (client.py's `close_manifest` falls back to `{}` in that
    case). There is no `wasSuccessful`/`errors`/`responseMessage` to read,
    so we cannot tell whether EPG actually closed the account or not — this
    must not be reported as a hard failure. Same "needs a human" precedent
    as the timeout case (D30)."""
    return response == {}


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


def parse_open_packages(response) -> list[dict]:
    """Normalise `GET /api/v1/Ship/Close`'s documented shape (F1):
    `[{"accountNumber": "...", "packageCount": n}]`. Tolerates `None`/empty
    (F2's 204 case) and a bare object in place of the array.
    """
    if not response:
        return []
    if isinstance(response, dict):
        response = [response]
    if not isinstance(response, list):
        return []

    result = []
    for item in response:
        if not isinstance(item, dict):
            continue
        account_number = item.get("accountNumber") or item.get("AccountNumber")
        raw_count = item.get("packageCount")
        if raw_count is None:
            raw_count = item.get("PackageCount")
        try:
            package_count = int(raw_count) if raw_count is not None else 0
        except (TypeError, ValueError):
            package_count = 0
        result.append(
            {
                "account_number": str(account_number) if account_number is not None else None,
                "package_count": package_count,
            }
        )
    return result


_CLOSE_ID_KEYS = ("closeId", "CloseId", "closeID", "close_id")
_CLOSE_REPORTS_KEYS = ("closeReports", "CloseReports", "closeReport", "close_reports")


def extract_close_id(response) -> str | None:
    """Defensive about casing and about the value living under `package`
    (F6: no real POST /Ship/Close response has ever been seen)."""
    if not isinstance(response, dict):
        return None
    for key in _CLOSE_ID_KEYS:
        value = response.get(key)
        if value:
            return str(value)
    package = response.get("package")
    if isinstance(package, dict):
        for key in _CLOSE_ID_KEYS:
            value = package.get(key)
            if value:
                return str(value)
    return None


def extract_close_reports(response):
    """Same defensiveness as `extract_close_id` — key casing and location
    are both guesses until Phase 4's first real close (F6)."""
    if not isinstance(response, dict):
        return None
    for key in _CLOSE_REPORTS_KEYS:
        if key in response and response[key] is not None:
            return response[key]
    package = response.get("package")
    if isinstance(package, dict):
        for key in _CLOSE_REPORTS_KEYS:
            if key in package and package[key] is not None:
                return package[key]
    return None


def extract_account_number(response: dict) -> str | None:
    """The EPG account number is returned for free in every rate/ship
    response (F3) — at `package.rates[].accountNumber` on sandbox, and at
    `package.selectedRate.accountNumber` observed on production. Used to
    auto-capture the number into settings rather than have an admin type it.
    """
    if not isinstance(response, dict):
        return None
    package = response.get("package")
    if not isinstance(package, dict):
        return None

    rates = package.get("rates")
    if isinstance(rates, list):
        for rate in rates:
            if isinstance(rate, dict) and rate.get("accountNumber"):
                return str(rate["accountNumber"])

    selected_rate = package.get("selectedRate")
    if isinstance(selected_rate, dict) and selected_rate.get("accountNumber"):
        return str(selected_rate["accountNumber"])

    if package.get("accountNumber"):
        return str(package["accountNumber"])

    return None


def truncate_long_strings(value, max_len: int = 2000):
    """Debugging-copy guard for `manifest_closes.epg_response_json` — same
    intent as `strip_image_payload`, but the close response's shape is
    unknown (F6), so this truncates any long string wherever it appears
    instead of targeting a specific known field.
    """
    if isinstance(value, str):
        if len(value) <= max_len:
            return value
        return f"{value[:max_len]}...<truncated, {len(value)} chars total>"
    if isinstance(value, dict):
        return {k: truncate_long_strings(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [truncate_long_strings(v, max_len) for v in value]
    return value


def strip_auth_header(request_body: dict) -> dict:
    """No-op placeholder: the auth header is never part of the JSON body, only headers.
    Kept as the single place D13's "strip credentials before storing" rule lives, in
    case a future EPG field structure ever needs a redaction pass.
    """
    return request_body

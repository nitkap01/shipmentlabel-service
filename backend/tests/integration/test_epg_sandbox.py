"""One real call against the EPG sandbox. Never run by default.

Opt in explicitly with:
    RUN_EPG_INTEGRATION_TESTS=1 EPG_API_KEY_SANDBOX=<real key> pytest -m integration

`conftest.py` sets a dummy EPG_API_KEY_SANDBOX for every other test, so
that alone cannot be the skip condition here — RUN_EPG_INTEGRATION_TESTS
is the explicit, separate opt-in. This test creates exactly one real
sandbox shipment and voids it in a `finally`, so it never leaves a live
label behind. It must never be pointed at the production base URL.
"""

import os

import pytest

from app.epg import client as epg_client
from app.epg import mapping as epg_mapping

pytestmark = pytest.mark.integration

RUN_INTEGRATION = os.environ.get("RUN_EPG_INTEGRATION_TESTS") == "1"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="set RUN_EPG_INTEGRATION_TESTS=1 to run against real EPG sandbox")
async def test_rate_then_ship_then_void_against_sandbox():
    request_body = {
        "serviceCode": "EP05",
        "referenceId": "INTEGRATION-TEST",
        "labelFormat": "PNG",
        "recipient": {
            "name": "Integration Test",
            "address1": "123 Main St",
            "city": "Newark",
            "postalCode": "07102",
            "stateOrProvince": "NJ",
            "countryCode": "US",
        },
        "from": {
            "company": "Green Shadow Enterprises",
            "address1": "293 Whitehead Rd",
            "city": "Trenton",
            "postalCode": "08619",
            "stateOrProvince": "NJ",
            "countryCode": "US",
        },
        "package": {
            "currencyCode": "USD",
            "value": "10.00",
            "weight": "16",
            "customs": epg_mapping.build_customs_block(10, "Integration Test"),
        },
    }

    rate_response, _ = await epg_client.rate("sandbox", request_body)
    assert "wasSuccessful" in rate_response

    ship_response, _ = await epg_client.ship("sandbox", request_body)
    assert epg_mapping.is_success(ship_response), ship_response

    unique_reference_id = epg_mapping.extract_unique_reference_id(ship_response)
    assert unique_reference_id
    assert epg_mapping.extract_tracking_number(ship_response)

    png_bytes = epg_mapping.extract_label_png(ship_response)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    try:
        pass
    finally:
        await epg_client.void("sandbox", unique_reference_id)

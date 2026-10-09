"""SHIP-5 discovery (SANDBOX ONLY): what does ePost answer to a void? Buys one free sandbox label, voids it, voids it
again, and voids a made-up id; prints the three answers (no label image). Never point this at production.
  RUN inside the backend environment with EPG_API_KEY_SANDBOX set:  python tools/void_probe.py
"""
import asyncio
import json

import httpx

from app.epg import client as epg
from app.epg import mapping

BODY = {   # same request as tests/integration/test_epg_sandbox.py
    "serviceCode": "EP05", "referenceId": "VOID-PROBE", "labelFormat": "PNG",
    "recipient": {"name": "Void Probe", "address1": "123 Main St", "city": "Newark", "postalCode": "07102",
                  "stateOrProvince": "NJ", "countryCode": "US"},
    "from": {"company": "Green Shadow Enterprises", "address1": "293 Whitehead Rd", "city": "Trenton",
             "postalCode": "08619", "stateOrProvince": "NJ", "countryCode": "US"},
    "package": {"currencyCode": "USD", "value": "10.00", "weight": "16",
                "customs": mapping.build_customs_block(10, "Void Probe")},
}


async def raw_void(uid):
    base, key = epg._base_url_and_key("sandbox")
    async with httpx.AsyncClient(timeout=30.0, verify=epg._verify_for(base)) as c:
        r = await c.get(f"{base}/api/v1/Ship/{uid}/Void", headers={"Authorization": f"Bearer {key}"})
    return r.status_code, r.text[:600]


async def main():
    ship, _ = await epg.ship("sandbox", BODY)
    print("ship ok:", mapping.is_success(ship), json.dumps(mapping.strip_image_payload(ship))[:400])
    uid = mapping.extract_unique_reference_id(ship)
    print("void #1:", await raw_void(uid))
    print("void #2 (again):", await raw_void(uid))
    print("void bogus id:", await raw_void("00000000-0000-0000-0000-000000000000"))


asyncio.run(main())

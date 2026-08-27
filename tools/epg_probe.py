"""One-off EPG sandbox probe (CLAUDE.md-governed Phase 0, gaps 1-3).

Never prints the API key. Reads it from EPG_API_KEY_SANDBOX (or falls back
to API_KEY, the original .env var name) in the environment.

Usage:
    export $(grep -v '^#' ../.env | xargs) 2>/dev/null
    python3 epg_probe.py rate            # confirm auth + inspect /rate response
    python3 epg_probe.py units           # differential weight test (lb vs oz guess)
    python3 epg_probe.py ship_and_void   # ONE real sandbox label, then void it
"""

import json
import os
import sys
import urllib.error
import urllib.request

SANDBOX_BASE = "https://test_api.epgparcels.com"
PRODUCTION_BASE = "https://api.epgparcels.com"

FROM = {
    "company": "Green Shadow Enterprises",
    "address1": "293 Whitehead Rd",
    "city": "Trenton",
    "postalCode": "08619",
    "stateOrProvince": "NJ",
    "countryCode": "US",
}

RECIPIENT = {
    "name": "Test Recipient",
    "address1": "123 Main St",
    "city": "Newark",
    "postalCode": "07102",
    "stateOrProvince": "NJ",
    "countryCode": "US",
}


def get_key():
    key = os.environ.get("EPG_API_KEY_SANDBOX") or os.environ.get("API_KEY")
    if not key:
        print("No EPG_API_KEY_SANDBOX / API_KEY in environment.", file=sys.stderr)
        sys.exit(1)
    return key


def call(base, path, method, body, key):
    url = f"{base}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, dict(resp.headers), resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()
    except urllib.error.URLError as e:
        return None, {}, str(e.reason)


def quota_lines(headers):
    return {k: v for k, v in headers.items() if k.lower().startswith("x-quota")}


def rate_request(weight):
    return {
        "serviceCode": "EP03",
        "referenceId": "PROBE-RATE",
        "labelFormat": "PNG",
        "recipient": RECIPIENT,
        "from": FROM,
        "package": {"currencyCode": "USD", "value": "10.00", "weight": str(weight)},
    }


def cmd_rate():
    key = get_key()
    for label, base in (("sandbox", SANDBOX_BASE), ("production", PRODUCTION_BASE)):
        status, headers, body = call(base, "/api/v1/rate", "POST", rate_request(1), key)
        print(f"--- {label} ({base}) ---")
        print("status:", status)
        print("quota:", quota_lines(headers))
        print("body:", body[:2000])
        print()


def cmd_units():
    key = get_key()
    for w in (1, 16):
        status, headers, body = call(SANDBOX_BASE, "/api/v1/rate", "POST", rate_request(w), key)
        print(f"weight={w} -> status={status} body={body[:1000]}")


def cmd_ship_and_void():
    key = get_key()
    ship_body = {
        "serviceCode": "EP03",
        "referenceId": "PROBE-SHIP-1",
        "labelFormat": "PNG",
        "recipient": RECIPIENT,
        "from": FROM,
        "package": {"currencyCode": "USD", "value": "10.00", "weight": "1"},
    }
    status, headers, body = call(SANDBOX_BASE, "/api/v1/ship", "POST", ship_body, key)
    print("ship status:", status)
    print("quota:", quota_lines(headers))
    try:
        parsed = json.loads(body)
        summary = {
            k: (f"<{type(v).__name__}, len={len(str(v))}>" if isinstance(v, str) and len(v) > 200 else v)
            for k, v in parsed.items()
        } if isinstance(parsed, dict) else parsed
        print("response keys/shape:", json.dumps(summary, indent=2)[:3000])
        ref_id = None
        if isinstance(parsed, dict):
            for candidate in ("uniqueReferenceId", "uniqueReferenceID", "id"):
                if candidate in parsed:
                    ref_id = parsed[candidate]
                    break
    except json.JSONDecodeError:
        print("body (not JSON):", body[:1000])
        ref_id = None

    if ref_id:
        vstatus, vheaders, vbody = call(SANDBOX_BASE, f"/api/v1/Ship/{ref_id}/Void", "GET", None, key)
        print("void status:", vstatus, "body:", vbody[:500])
    else:
        print("No uniqueReferenceId found in response — void skipped, inspect body above.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "rate"
    {"rate": cmd_rate, "units": cmd_units, "ship_and_void": cmd_ship_and_void}[cmd]()

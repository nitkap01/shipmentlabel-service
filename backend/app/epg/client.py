"""HTTP client for the ePost Global (EPG) Shipping API.

Base URLs and auth confirmed against the vendor doc (documents/ePost API
document.pdf) and empirically verified against the sandbox host on
2026-08-27 (see the task doc). The EPG key never leaves this module's
request headers: it is not logged and not persisted anywhere.
"""

import ssl

import httpx

from app.config import settings

SANDBOX_BASE_URL = "https://test_api.epgparcels.com"
PRODUCTION_BASE_URL = "https://api.epgparcels.com"

QUOTA_HEADER_PREFIX = "x-quota-"

# EPG's sandbox hostname contains an underscore, which is not a valid DNS
# label character (RFC 952/1123). Confirmed via `openssl s_client` + curl on
# 2026-08-27 that the server presents a normal, validly-chained wildcard
# certificate (CN=*.epgparcels.com) — Python's stricter ssl module refuses to
# match that wildcard against the underscore label, where curl's OpenSSL CLI
# does not. This context keeps full certificate-chain verification (still
# requires a certificate trusted by the system CA store) and disables only
# the hostname-label match, which is the one check that cannot pass against
# a non-RFC-compliant hostname EPG controls, not ours. Never used for the
# production host, which has a normal hostname.
_SANDBOX_SSL_CONTEXT = ssl.create_default_context()
_SANDBOX_SSL_CONTEXT.check_hostname = False
_SANDBOX_SSL_CONTEXT.verify_mode = ssl.CERT_REQUIRED


def _verify_for(base_url: str):
    return _SANDBOX_SSL_CONTEXT if base_url == SANDBOX_BASE_URL else True


class EPGError(Exception):
    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class EPGTimeoutError(EPGError):
    """A network-level failure (timeout, connection reset) with no HTTP response.

    Ambiguous, not a definite failure (D8): EPG may or may not have actually
    created the shipment. Callers must never auto-retry on this — the caller
    (labels_service.create_label) leaves the label `pending` for a human to
    check, rather than marking it `failed` (which would imply it's safe to
    resubmit).
    """


class EPGNotConfiguredError(EPGError):
    pass


def _base_url_and_key(environment: str) -> tuple[str, str]:
    if environment == "production":
        if not settings.epg_api_key_production:
            raise EPGNotConfiguredError("No EPG_API_KEY_PRODUCTION configured")
        return PRODUCTION_BASE_URL, settings.epg_api_key_production

    if not settings.epg_api_key_sandbox:
        raise EPGNotConfiguredError("No EPG_API_KEY_SANDBOX configured")
    return SANDBOX_BASE_URL, settings.epg_api_key_sandbox


def quota_from_headers(headers: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower().startswith(QUOTA_HEADER_PREFIX)}


async def _post(environment: str, path: str, body: dict) -> tuple[dict, dict[str, str]]:
    base_url, key = _base_url_and_key(environment)
    async with httpx.AsyncClient(timeout=30.0, verify=_verify_for(base_url)) as client:
        try:
            resp = await client.post(
                f"{base_url}{path}",
                json=body,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.RequestError as exc:
            raise EPGTimeoutError(f"Network error calling EPG: {exc}") from exc

    quota = quota_from_headers(resp.headers)
    try:
        data = resp.json()
    except ValueError:
        raise EPGError(f"Non-JSON response from EPG (HTTP {resp.status_code})", status_code=resp.status_code)

    if resp.status_code >= 400:
        raise EPGError(
            data.get("message", f"EPG HTTP {resp.status_code}"),
            status_code=resp.status_code,
        )

    return data, quota


async def rate(environment: str, body: dict) -> tuple[dict, dict[str, str]]:
    return await _post(environment, "/api/v1/rate", body)


async def ship(environment: str, body: dict) -> tuple[dict, dict[str, str]]:
    return await _post(environment, "/api/v1/ship", body)


async def list_open(environment: str) -> tuple[list | dict, dict[str, str]]:
    """`GET /api/v1/Ship/Close` — account number + open package count (F1).

    With nothing open, EPG answers `HTTP 204 No Content` with an empty body
    (F2) — this is the ordinary "nothing open" state, not an error, so it is
    normalised to `([], quota)` rather than raising on `.json()`.
    """
    base_url, key = _base_url_and_key(environment)
    async with httpx.AsyncClient(timeout=30.0, verify=_verify_for(base_url)) as client:
        try:
            resp = await client.get(
                f"{base_url}/api/v1/Ship/Close",
                headers={"Authorization": f"Bearer {key}"},
            )
        except httpx.RequestError as exc:
            raise EPGTimeoutError(f"Network error calling EPG: {exc}") from exc

    quota = quota_from_headers(resp.headers)

    if resp.status_code >= 400:
        raise EPGError(f"EPG HTTP {resp.status_code}", status_code=resp.status_code)

    if resp.status_code == 204 or not resp.content:
        return [], quota

    try:
        data = resp.json()
    except ValueError:
        return [], quota

    return data if data is not None else [], quota


async def close_manifest(environment: str, account_number: str) -> tuple[dict, dict[str, str]]:
    """`POST /api/v1/Ship/Close?accountNumber=<n>` — no JSON request body, so
    `_post()` cannot be reused. Response shape is unverified (F6, close is a
    real stateful carrier action never yet called from this app), so an
    empty/non-JSON body is tolerated the same way `list_open` tolerates one.
    """
    base_url, key = _base_url_and_key(environment)
    async with httpx.AsyncClient(timeout=30.0, verify=_verify_for(base_url)) as client:
        try:
            resp = await client.post(
                f"{base_url}/api/v1/Ship/Close",
                params={"accountNumber": account_number},
                headers={"Authorization": f"Bearer {key}"},
            )
        except httpx.RequestError as exc:
            raise EPGTimeoutError(f"Network error calling EPG: {exc}") from exc

    quota = quota_from_headers(resp.headers)

    if resp.status_code >= 400:
        try:
            error_data = resp.json()
        except ValueError:
            error_data = {}
        message = error_data.get("message") if isinstance(error_data, dict) else None
        raise EPGError(message or f"EPG HTTP {resp.status_code}", status_code=resp.status_code)

    if not resp.content:
        return {}, quota

    try:
        data = resp.json()
    except ValueError:
        return {}, quota

    return data if isinstance(data, dict) else {}, quota


async def void(environment: str, unique_reference_id: str) -> dict:
    base_url, key = _base_url_and_key(environment)
    async with httpx.AsyncClient(timeout=30.0, verify=_verify_for(base_url)) as client:
        try:
            resp = await client.get(
                f"{base_url}/api/v1/Ship/{unique_reference_id}/Void",
                headers={"Authorization": f"Bearer {key}"},
            )
        except httpx.RequestError as exc:
            raise EPGTimeoutError(f"Network error calling EPG: {exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        raise EPGError(f"Non-JSON response from EPG (HTTP {resp.status_code})", status_code=resp.status_code)

    if resp.status_code >= 400:  # e.g. 404 {"message": "...does not exist or has already been voided."}
        message = data.get("message") if isinstance(data, dict) else None
        raise EPGError(message or str(data), status_code=resp.status_code)

    return data

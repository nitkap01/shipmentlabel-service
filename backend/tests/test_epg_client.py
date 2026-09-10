import httpx
import pytest

from app.epg import client as epg_client


def _install_mock_transport(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    class PatchedAsyncClient(real_async_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(epg_client.httpx, "AsyncClient", PatchedAsyncClient)


async def test_close_manifest_surfaces_epg_error_message(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"message": "0 active unclosed packages were found for the given account number"},
        )

    _install_mock_transport(monkeypatch, handler)

    with pytest.raises(epg_client.EPGError) as exc_info:
        await epg_client.close_manifest("sandbox", "11191")

    assert exc_info.value.message == "0 active unclosed packages were found for the given account number"
    assert exc_info.value.status_code == 400


async def test_close_manifest_falls_back_to_generic_message_on_non_json_error_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal server error")

    _install_mock_transport(monkeypatch, handler)

    with pytest.raises(epg_client.EPGError) as exc_info:
        await epg_client.close_manifest("sandbox", "11191")

    assert exc_info.value.message == "EPG HTTP 500"


async def test_close_manifest_falls_back_to_generic_message_on_non_dict_error_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=["unexpected", "array", "body"])

    _install_mock_transport(monkeypatch, handler)

    with pytest.raises(epg_client.EPGError) as exc_info:
        await epg_client.close_manifest("sandbox", "11191")

    assert exc_info.value.message == "EPG HTTP 400"


async def test_close_manifest_tolerates_empty_success_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    _install_mock_transport(monkeypatch, handler)

    data, quota = await epg_client.close_manifest("sandbox", "11191")
    assert data == {}

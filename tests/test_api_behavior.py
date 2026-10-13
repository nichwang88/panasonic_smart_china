"""Test transport security and response validation without network access."""

import asyncio
from types import SimpleNamespace

import aiohttp
import pytest

from custom_components.panasonic_smart_china import api
from custom_components.panasonic_smart_china.profiles.fridge_0100_fridge_43 import (
    FRIDGE_0100_FRIDGE_43_PROFILE,
)


class Response:
    status = 200

    def __init__(self, data):
        self.data = data
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def json(self):
        return self.data

    async def text(self):
        return "response"


class Request:
    """Support both the old awaited request and the context-manager API."""

    def __init__(self, response):
        self.response = response

    def __await__(self):
        async def get():
            return self.response
        return get().__await__()

    async def __aenter__(self):
        return await self.response.__aenter__()

    async def __aexit__(self, *args):
        return await self.response.__aexit__(*args)


def client(monkeypatch, response):
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return Request(response)
    monkeypatch.setattr(api, "async_get_clientsession", lambda hass: SimpleNamespace(post=post))
    return api.PanasonicApiClient(None, "fake-session"), calls


def test_requests_verify_pinned_certificate_and_close_response(monkeypatch):
    response = Response({"results": {}})
    device, calls = client(monkeypatch, response)
    asyncio.run(device._post(api.URL_GET_TOKEN, {}, headers={}, require_results=True))
    assert isinstance(calls[0]["ssl"], aiohttp.Fingerprint)
    assert calls[0]["ssl"].fingerprint.hex() == "a03226da8dd2ef0ea7e390232eed88d27d36c9e1a3208439f20a4c37eec35948"
    assert calls[0]["allow_redirects"] is False
    assert response.closed


@pytest.mark.parametrize("status", [401, 403])
def test_http_auth_failure_is_distinguished(monkeypatch, status):
    response = Response({})
    response.status = status
    device, _ = client(monkeypatch, response)
    with pytest.raises(api.PanasonicApiAuthError):
        asyncio.run(device._post(api.URL_GET_TOKEN, {}, headers={}, require_results=True))


def test_empty_fridge_status_is_rejected(monkeypatch):
    device, _ = client(monkeypatch, Response({"results": {}}))
    with pytest.raises(api.PanasonicApiResponseError):
        asyncio.run(device.get_device_status(FRIDGE_0100_FRIDGE_43_PROFILE, "fake", "fake", "fake"))


def test_certificate_mismatch_fails_without_retry(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        raise aiohttp.ServerFingerprintMismatch(b"a" * 32, b"b" * 32, "fake", 443)
    monkeypatch.setattr(api, "async_get_clientsession", lambda hass: SimpleNamespace(post=post))
    with pytest.raises(api.PanasonicApiResponseError):
        asyncio.run(api.PanasonicApiClient(None)._post(api.URL_GET_TOKEN, {}, headers={}, require_results=True))
    assert len(calls) == 1

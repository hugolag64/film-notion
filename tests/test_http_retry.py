import asyncio

from backend.core import http


class FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def request(self, method, url, **kwargs):
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


def _patch(monkeypatch, client):
    monkeypatch.setattr(http, "get_client", lambda: client)

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(http.asyncio, "sleep", _no_sleep)


def test_retries_on_429_then_succeeds(monkeypatch):
    client = FakeClient([FakeResponse(429), FakeResponse(429), FakeResponse(200)])
    _patch(monkeypatch, client)

    resp = asyncio.run(http.request_with_retry("GET", "http://x", base_delay=0.01))
    assert resp.status_code == 200
    assert client.calls == 3


def test_gives_up_after_max_retries(monkeypatch):
    client = FakeClient([FakeResponse(429)] * 10)
    _patch(monkeypatch, client)

    resp = asyncio.run(http.request_with_retry("GET", "http://x", max_retries=3, base_delay=0.01))
    assert resp.status_code == 429
    assert client.calls == 3


def test_respects_retry_after_header(monkeypatch):
    captured = {}

    client = FakeClient([FakeResponse(429, {"Retry-After": "2"}), FakeResponse(200)])
    monkeypatch.setattr(http, "get_client", lambda: client)

    async def _capture_sleep(seconds):
        captured["seconds"] = seconds

    monkeypatch.setattr(http.asyncio, "sleep", _capture_sleep)

    resp = asyncio.run(http.request_with_retry("GET", "http://x"))
    assert resp.status_code == 200
    assert captured["seconds"] == 2.0

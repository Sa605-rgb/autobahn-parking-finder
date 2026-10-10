"""Client tests never call the real Autobahn API."""

import asyncio

import httpx

from parking_finder.api import AutobahnClient, AutobahnError


def _run(coro):
    return asyncio.run(coro)


def _client(handler) -> AutobahnClient:
    return AutobahnClient(transport=httpx.MockTransport(handler), base_url="https://example.test")


def test_list_roads_sorts_and_ignores_junk():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/"
        return httpx.Response(200, json={"roads": ["A10", "A2", "", "A2", 5, "A1"]})

    async def scenario():
        client = _client(handler)
        try:
            return await client.list_roads()
        finally:
            await client.aclose()

    assert _run(scenario()) == ["A1", "A2", "A10"]


def test_empty_and_missing_roads_do_not_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/webcam"):
            return httpx.Response(204)
        if "missing" in request.url.path:
            return httpx.Response(404)
        if request.url.path.endswith("/parking_lorry"):
            return httpx.Response(200, content=b"")
        return httpx.Response(200, json={})

    async def scenario():
        client = _client(handler)
        try:
            empty = await client.webcams("A7")
            missing = await client.parking("missing")
            blank = await client.roadworks("A7")
            return empty, missing, blank
        finally:
            await client.aclose()

    assert _run(scenario()) == ({}, {}, {})


def test_timeout_and_bad_json_become_autobahn_errors():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    def json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    def ssl_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("certificate verify failed", request=request)

    async def expect(handler, kind: str) -> None:
        client = _client(handler)
        try:
            await client.list_roads()
        except AutobahnError as exc:
            assert exc.kind == kind
        else:
            raise AssertionError("expected AutobahnError")
        finally:
            await client.aclose()

    _run(expect(timeout_handler, "timeout"))
    _run(expect(json_handler, "parse"))
    _run(expect(ssl_handler, "ssl"))


def test_http_error_and_partial_road_load():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/parking_lorry"):
            return httpx.Response(200, json={"parking_lorry": [{"subtitle": "West", "coordinate": {"lat": 51, "long": 10}}]})
        if path.endswith("/webcam"):
            return httpx.Response(500)
        return httpx.Response(200, json={})

    async def scenario():
        client = _client(handler)
        try:
            return await client.load_road("A7")
        finally:
            await client.aclose()

    bundle = _run(scenario())
    parking, parking_error = bundle["parking"]
    _webcams, webcam_error = bundle["webcams"]
    assert parking_error is None
    assert parking["parking_lorry"][0]["subtitle"] == "West"
    assert webcam_error is not None
    assert "500" in webcam_error


def test_load_settings_rejects_bad_port(monkeypatch):
    from parking_finder.settings import load_settings

    monkeypatch.setenv("PORT", "nope")
    try:
        load_settings()
    except SystemExit as exc:
        assert "PORT" in str(exc)
    else:
        raise AssertionError("expected SystemExit")

import asyncio

import httpx

from api.index import app as vercel_app
from backend.app import app


def request(method: str, path: str, **kwargs):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_health_endpoint_does_not_need_youtube():
    response = request("GET", "/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_vercel_entrypoint_exposes_complete_api_paths():
    assert vercel_app is app
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/api/health", "GET") in routes
    assert ("/api/inspect", "POST") in routes
    assert ("/api/transcript", "POST") in routes


def test_inspection_endpoint_validates_input():
    response = request(
        "POST", "/api/inspect", json={"url": "https://example.com", "latest_videos": 10}
    )
    assert response.status_code == 422


def test_transcript_endpoint_rejects_channel_urls():
    response = request(
        "POST",
        "/api/transcript",
        json={"url": "https://www.youtube.com/@ExampleChannel", "language": "en"},
    )
    assert response.status_code == 422

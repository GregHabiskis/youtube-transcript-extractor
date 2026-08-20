import asyncio

import httpx

from api.index import app as vercel_app
from backend.app import app
from backend.transcripts.models import TranscriptBlock
from backend.youtube.models import VideoMetadata
from backend.youtube.service import TranscriptOutput


def request(method: str, path: str, **kwargs):
    async def send():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
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


def test_transcript_endpoint_serializes_successful_output(monkeypatch):
    output = TranscriptOutput(
        video=VideoMetadata(
            id="BaW_jenozKc",
            title="Test video",
            url="https://www.youtube.com/watch?v=BaW_jenozKc",
            channel="Test channel",
        ),
        source="manual",
        language="en",
        format="json3",
        blocks=[TranscriptBlock(0, 1000, "hello")],
        transcript="hello",
    )
    monkeypatch.setattr("backend.app.youtube.extract_transcript", lambda *_args: output)

    response = request(
        "POST",
        "/api/transcript",
        json={"url": "https://www.youtube.com/watch?v=BaW_jenozKc", "language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert response.json()["format"] == "json3"
    assert response.json()["blocks"] == [{"start_ms": 0, "end_ms": 1000, "text": "hello"}]


def test_unexpected_transcript_errors_remain_internal(monkeypatch):
    def explode(*_args):
        raise RuntimeError("unexpected parser failure")

    monkeypatch.setattr("backend.app.youtube.extract_transcript", explode)

    response = request(
        "POST",
        "/api/transcript",
        json={"url": "https://www.youtube.com/watch?v=BaW_jenozKc", "language": "en"},
    )
    assert response.status_code == 500
    assert response.json() == {
        "status": "failed",
        "code": "INTERNAL_ERROR",
        "error": "The server could not complete that request.",
    }

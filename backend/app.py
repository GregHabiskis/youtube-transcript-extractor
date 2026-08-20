from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api_models import InspectRequest, TranscriptRequest
from backend.youtube.errors import InvalidYouTubeURL, TranscriptExtractionError, YouTubeServiceError
from backend.youtube.service import YouTubeService

log_level = os.environ.get("YTVID_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT_DIR / "dist"

app = FastAPI(
    title="YTVID Transcript Extractor API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
)
youtube = YouTubeService()
MAX_REQUEST_BYTES = 64 * 1024


@app.middleware("http")
async def limit_request_size(request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > MAX_REQUEST_BYTES
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse(
                status_code=413,
                content={"status": "failed", "error": "Request payload is too large."},
            )
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/inspect")
def inspect_source(request: InspectRequest) -> dict:
    try:
        result = youtube.inspect(request.url, request.latest_videos)
    except InvalidYouTubeURL as exc:
        raise HTTPException(status_code=422, detail=exc.public_message) from exc
    except YouTubeServiceError as exc:
        logger.warning("Inspection rejected: %s", exc.public_message)
        raise HTTPException(status_code=502, detail=exc.public_message) from exc
    return result.to_dict()


@app.post("/api/transcript")
def transcript(request: TranscriptRequest) -> dict:
    try:
        result = youtube.extract_transcript(request.url, request.language)
    except InvalidYouTubeURL as exc:
        raise HTTPException(status_code=422, detail=exc.public_message) from exc
    except TranscriptExtractionError as exc:
        logger.warning("Transcript request failed: %s", exc.public_message)
        return JSONResponse(
            status_code=502,
            content={"status": "failed", "code": exc.code, "error": exc.public_message},
        )
    except YouTubeServiceError as exc:
        logger.warning("Transcript request rejected: %s", exc.public_message)
        return JSONResponse(
            status_code=502,
            content={"status": "failed", "code": exc.code, "error": exc.public_message},
        )
    return result.to_dict()


@app.exception_handler(Exception)
async def unhandled_error(_request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error")
    return JSONResponse(
        status_code=500,
        content={
            "status": "failed",
            "code": "INTERNAL_ERROR",
            "error": "The server could not complete that request.",
        },
    )


def _mount_frontend() -> None:
    if not DIST_DIR.is_dir():
        return

    # FastAPI's frontend helper is the current Vercel-supported integration and
    # includes SPA fallback behavior. The StaticFiles branch keeps the same app
    # usable under plain local Uvicorn if an older FastAPI is installed.
    frontend = getattr(app, "frontend", None)
    if callable(frontend):
        frontend("/", directory=DIST_DIR)
    else:
        app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")


if DIST_DIR.is_dir():
    _mount_frontend()

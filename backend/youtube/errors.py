from __future__ import annotations


class YouTubeServiceError(RuntimeError):
    """Base error whose message is safe to expose to the browser."""

    code = "YOUTUBE_SERVICE_ERROR"

    def __init__(
        self,
        public_message: str,
        *,
        cause: Exception | None = None,
        code: str | None = None,
    ):
        super().__init__(public_message)
        self.public_message = public_message
        self.cause = cause
        self.code = code or type(self).code


class InvalidYouTubeURL(YouTubeServiceError):
    code = "INVALID_URL"


class YouTubeDiscoveryError(YouTubeServiceError):
    code = "YOUTUBE_EXTRACTION_FAILED"


class TranscriptUnavailable(YouTubeServiceError):
    code = "NO_CAPTIONS"

    def __init__(self, public_message: str = "No transcript available for this video."):
        super().__init__(public_message)


class TranscriptExtractionError(YouTubeServiceError):
    code = "INTERNAL_ERROR"

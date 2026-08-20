from __future__ import annotations


class YouTubeServiceError(RuntimeError):
    """Base error whose message is safe to expose to the browser."""

    def __init__(self, public_message: str, *, cause: Exception | None = None):
        super().__init__(public_message)
        self.public_message = public_message
        self.cause = cause


class InvalidYouTubeURL(YouTubeServiceError):
    pass


class YouTubeDiscoveryError(YouTubeServiceError):
    pass


class TranscriptUnavailable(YouTubeServiceError):
    def __init__(self, public_message: str = "No transcript available for this video."):
        super().__init__(public_message)


class TranscriptExtractionError(YouTubeServiceError):
    pass

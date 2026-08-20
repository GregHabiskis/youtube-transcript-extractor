from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from .errors import InvalidYouTubeURL

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]{1,100}$")
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{4,}$")
LEGACY_CHANNEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
YOUTU_BE_HOSTS = {"youtu.be", "www.youtu.be"}


@dataclass(frozen=True, slots=True)
class NormalizedURL:
    kind: Literal["channel", "video"]
    url: str
    video_id: str | None = None
    channel_path: str | None = None


def normalize_youtube_url(raw_url: str) -> NormalizedURL:
    """Validate and canonicalize a supported YouTube URL.

    The parser intentionally accepts only YouTube hosts. This keeps the API from
    becoming an arbitrary URL fetcher while allowing channel roots to behave as
    their normal uploads/videos feed.
    """

    value = raw_url.strip()
    if not value:
        raise InvalidYouTubeURL("Enter a YouTube URL.")
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = f"https://{value}"

    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise InvalidYouTubeURL("That URL is not valid.", cause=exc) from exc

    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise InvalidYouTubeURL("Use an http(s) YouTube URL.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidYouTubeURL("That URL contains an invalid port.") from exc
    if parsed.username or parsed.password or port:
        raise InvalidYouTubeURL("YouTube URLs cannot include credentials or a custom port.")
    if host not in YOUTUBE_HOSTS and host not in YOUTU_BE_HOSTS:
        raise InvalidYouTubeURL("Only youtube.com and youtu.be URLs are supported.")

    if host in YOUTU_BE_HOSTS:
        return _normalize_short_url(parsed)
    return _normalize_youtube_host(parsed)


def _normalize_short_url(parsed) -> NormalizedURL:
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) != 1 or not VIDEO_ID_RE.fullmatch(parts[0]):
        raise InvalidYouTubeURL("That youtu.be URL does not contain a valid video ID.")
    video_id = parts[0]
    return NormalizedURL("video", f"https://www.youtube.com/watch?v={video_id}", video_id=video_id)


def _normalize_youtube_host(parsed) -> NormalizedURL:
    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    first = path_parts[0].lower() if path_parts else ""
    query = parse_qs(parsed.query)

    if first in {"watch", "watch_popup.php", "movie"}:
        video_id = _first_query_value(query, "v")
        return _video_result(video_id)

    if first in {"shorts", "live", "embed", "v", "e"}:
        if len(path_parts) != 2:
            raise InvalidYouTubeURL("That YouTube video URL does not contain a valid video ID.")
        return _video_result(path_parts[1])

    if first == "playlist":
        raise InvalidYouTubeURL("Playlist URLs are not supported; use a channel or video URL.")

    if first in {"channel", "user", "c"}:
        if len(path_parts) not in {2, 3} or (
            len(path_parts) == 3 and path_parts[2].lower() != "videos"
        ):
            raise InvalidYouTubeURL(
                "Use a channel root URL or its /videos tab, not Shorts or Live."
            )
        identifier = path_parts[1]
        if first == "channel" and not CHANNEL_ID_RE.fullmatch(identifier):
            raise InvalidYouTubeURL("That channel URL does not contain a valid channel ID.")
        if first in {"user", "c"} and not LEGACY_CHANNEL_RE.fullmatch(identifier):
            raise InvalidYouTubeURL("That channel URL contains an invalid channel name.")
        return _channel_result(f"{first}/{identifier}")

    if path_parts and HANDLE_RE.fullmatch(path_parts[0]):
        if len(path_parts) not in {1, 2} or (
            len(path_parts) == 2 and path_parts[1].lower() != "videos"
        ):
            raise InvalidYouTubeURL(
                "Use a channel root URL or its /videos tab, not Shorts or Live."
            )
        return _channel_result(path_parts[0])

    # A bare ?v=... URL is accepted by yt-dlp, but only when it is on YouTube.
    if not path_parts:
        video_id = _first_query_value(query, "v")
        if video_id:
            return _video_result(video_id)

    raise InvalidYouTubeURL(
        "Use a YouTube channel URL, a channel /videos URL, or an individual video URL."
    )


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _video_result(video_id: str | None) -> NormalizedURL:
    if not video_id or not VIDEO_ID_RE.fullmatch(video_id):
        raise InvalidYouTubeURL("That YouTube URL does not contain a valid 11-character video ID.")
    return NormalizedURL("video", f"https://www.youtube.com/watch?v={video_id}", video_id=video_id)


def _channel_result(channel_path: str) -> NormalizedURL:
    canonical_path = "/" + channel_path.strip("/") + "/videos"
    return NormalizedURL(
        "channel",
        urlunsplit(("https", "www.youtube.com", canonical_path, "", "")),
        channel_path=channel_path,
    )

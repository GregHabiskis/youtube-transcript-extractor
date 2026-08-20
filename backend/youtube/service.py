from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from backend.transcripts.cleaner import clean_cues, merge_paragraphs
from backend.transcripts.json3 import SubtitleParseError, parse_json3
from backend.transcripts.models import TranscriptBlock
from backend.transcripts.renderer import render_plaintext
from backend.transcripts.vtt import parse_vtt

from .errors import (
    InvalidYouTubeURL,
    TranscriptExtractionError,
    YouTubeDiscoveryError,
    YouTubeServiceError,
)
from .models import InspectionResult, VideoMetadata
from .urls import normalize_youtube_url

logger = logging.getLogger(__name__)

LANGUAGE_RE = re.compile(r"^[A-Za-z0-9]{1,8}(?:[-_][A-Za-z0-9]{1,8}){0,4}$")
SUBTITLE_FORMAT_PREFERENCE = ("json3", "vtt", "srt")
MAX_SUBTITLE_BYTES = 8 * 1024 * 1024


class _YtDlpLogger:
    def debug(self, message: str) -> None:
        if message.startswith("[debug] "):
            logger.debug("yt-dlp %s", message[8:])

    def warning(self, message: str) -> None:
        logger.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        logger.error("yt-dlp: %s", message)


class TranscriptOutput:
    def __init__(
        self,
        *,
        video: VideoMetadata,
        source: str | None,
        language: str | None,
        blocks: list[TranscriptBlock],
        transcript: str,
        status: str = "complete",
        reason: str | None = None,
    ) -> None:
        self.video = video
        self.source = source
        self.language = language
        self.blocks = blocks
        self.transcript = transcript
        self.status = status
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "video": self.video.to_dict(),
            "source": self.source,
            "language": self.language,
            "transcript": self.transcript,
            "blocks": [
                {
                    "start_ms": block.start_ms,
                    "end_ms": block.end_ms,
                    "text": block.text,
                }
                for block in self.blocks
            ],
            "reason": self.reason,
        }


class YouTubeService:
    """Small, stateless wrapper around yt-dlp's Python API."""

    def inspect(self, raw_url: str, latest_videos: int) -> InspectionResult:
        normalized = normalize_youtube_url(raw_url)
        if normalized.kind == "video":
            try:
                info = self._extract_info(
                    normalized.url,
                    {"noplaylist": True, "ignore_no_formats_error": True},
                )
            except Exception as exc:
                logger.exception("Video inspection failed for %s", normalized.url)
                raise YouTubeDiscoveryError(
                    _public_yt_error(exc, "Could not inspect that YouTube video."), cause=exc
                ) from exc
            if not _has_real_title(info):
                raise YouTubeDiscoveryError("This YouTube video is unavailable or restricted.")
            video = self._video_from_info(info, fallback_url=normalized.url, index=1)
            if video is None:
                raise YouTubeDiscoveryError("YouTube returned incomplete video information.")
            channel = video.channel or "Unknown channel"
            return InspectionResult(
                kind="video",
                source_url=normalized.url,
                channel=channel,
                channel_url=video.channel_url,
                videos=[video],
                requested_count=1,
            )

        if latest_videos < 1:
            raise YouTubeDiscoveryError("The number of latest videos must be a positive number.")

        options = self._base_options()
        options.update(
            {
                "extract_flat": True,
                "lazy_playlist": True,
                "playlist_items": f"1:{latest_videos}",
                "noplaylist": False,
                "ignoreerrors": True,
            }
        )
        try:
            with YoutubeDL(options) as ydl:
                result = ydl.extract_info(normalized.url, download=False)
        except Exception as exc:  # yt-dlp has several extractor-specific exception types.
            logger.exception("Channel discovery failed for %s", normalized.url)
            raise YouTubeDiscoveryError(
                _public_yt_error(exc, "Could not inspect that YouTube channel."), cause=exc
            ) from exc

        if not result:
            raise YouTubeDiscoveryError("YouTube returned no channel information.")

        channel = (
            _string_value(result.get("channel") or result.get("uploader")) or "Unknown channel"
        )
        channel_url = _string_value(result.get("channel_url") or result.get("uploader_url"))
        videos: list[VideoMetadata] = []
        seen_ids: set[str] = set()
        entries = result.get("entries") or []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            video = self._video_from_info(entry, fallback_channel=channel)
            if not video or video.id in seen_ids or not _is_normal_video_entry(entry, video.url):
                continue
            seen_ids.add(video.id)
            videos.append(
                VideoMetadata(
                    id=video.id,
                    title=video.title,
                    url=video.url,
                    channel=video.channel or channel,
                    channel_url=video.channel_url or channel_url,
                    upload_date=video.upload_date,
                    duration_seconds=video.duration_seconds,
                    thumbnail=video.thumbnail,
                    index=len(videos) + 1,
                )
            )
            if len(videos) >= latest_videos:
                break

        if not videos:
            raise YouTubeDiscoveryError(
                "No normal videos were found. The channel may be empty, private, or unavailable."
            )

        return InspectionResult(
            kind="channel",
            source_url=normalized.url,
            channel=channel,
            channel_url=channel_url,
            videos=videos,
            requested_count=latest_videos,
        )

    def extract_transcript(self, raw_url: str, language: str) -> TranscriptOutput:
        normalized = normalize_youtube_url(raw_url)
        if normalized.kind != "video":
            raise InvalidYouTubeURL(
                "Transcript extraction requires an individual YouTube video URL."
            )
        language = validate_language(language)

        try:
            info = self._extract_info(
                normalized.url,
                {
                    "noplaylist": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitlesformat": "json3/vtt/srt",
                    "ignore_no_formats_error": True,
                },
            )
        except YouTubeServiceError:
            raise
        except Exception as exc:
            logger.exception("Transcript extraction failed for %s", normalized.url)
            raise TranscriptExtractionError(
                _public_yt_error(exc, "Could not extract this video."), cause=exc
            ) from exc

        if not _has_real_title(info):
            raise TranscriptExtractionError("This YouTube video is unavailable or restricted.")
        video = self._video_from_info(info, fallback_url=normalized.url, index=1)
        if video is None:
            raise TranscriptExtractionError("YouTube returned incomplete video information.")
        source, selected_language, track = _select_track(
            info.get("subtitles"), info.get("automatic_captions"), language
        )
        if not source or not selected_language or not track:
            return TranscriptOutput(
                video=video,
                source=None,
                language=None,
                blocks=[],
                transcript="",
                status="no_captions",
                reason=(
                    "No captions were found for the selected language."
                    if language != "auto"
                    else "No captions are available for this video."
                ),
            )

        cues = self._download_and_parse_track(track, info)
        cleaned = clean_cues(cues)
        blocks = merge_paragraphs(cleaned)
        if not blocks:
            return TranscriptOutput(
                video=video,
                source=None,
                language=None,
                blocks=[],
                transcript="",
                status="no_captions",
                reason="The caption track contained no spoken text.",
            )

        transcript = render_plaintext(
            title=video.title,
            channel=video.channel,
            url=video.url,
            upload_date=video.upload_date,
            source=source,
            language=selected_language,
            blocks=blocks,
        )
        return TranscriptOutput(
            video=video,
            source=source,
            language=selected_language,
            blocks=blocks,
            transcript=transcript,
        )

    def _extract_info(
        self, url: str, extra_options: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        options = self._base_options()
        if extra_options:
            options.update(extra_options)
        with YoutubeDL(options) as ydl:
            result = ydl.extract_info(url, download=False)
        if not isinstance(result, Mapping):
            raise YouTubeServiceError("yt-dlp returned no video information.")
        return result

    @staticmethod
    def _base_options() -> dict[str, Any]:
        return {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 20,
            "retries": 2,
            "extractor_retries": 2,
            "fragment_retries": 2,
            "check_formats": False,
            "logger": _YtDlpLogger(),
        }

    @staticmethod
    def _video_from_info(
        info: Mapping[str, Any],
        *,
        fallback_url: str | None = None,
        fallback_channel: str | None = None,
        index: int | None = None,
    ) -> VideoMetadata | None:
        video_id = _string_value(info.get("id"))
        if not video_id:
            return None
        url = (
            fallback_url
            or _string_value(info.get("webpage_url"))
            or f"https://www.youtube.com/watch?v={video_id}"
        )
        with suppress(InvalidYouTubeURL):
            url = normalize_youtube_url(url).url
        title = _string_value(info.get("title")) or f"YouTube video {video_id}"
        channel = (
            _string_value(info.get("channel") or info.get("uploader"))
            or fallback_channel
            or "Unknown channel"
        )
        channel_url = _string_value(info.get("channel_url") or info.get("uploader_url"))
        upload_date = _format_upload_date(info.get("upload_date"))
        thumbnail = _string_value(info.get("thumbnail"))
        duration = _number_value(info.get("duration"))
        return VideoMetadata(
            id=video_id,
            title=title,
            url=url,
            channel=channel,
            channel_url=channel_url,
            upload_date=upload_date,
            duration_seconds=duration,
            thumbnail=thumbnail,
            index=index,
        )

    @staticmethod
    def _download_and_parse_track(track: Mapping[str, Any], info: Mapping[str, Any]) -> list:
        raw_data = track.get("data")
        if raw_data is None:
            url = track.get("url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                raise TranscriptExtractionError("yt-dlp returned an invalid subtitle URL.")
            if not _is_allowed_caption_url(url):
                raise TranscriptExtractionError("yt-dlp returned a caption URL outside YouTube.")
            options = YouTubeService._base_options()
            options["http_headers"] = info.get("http_headers") or {}
            try:
                with YoutubeDL(options) as ydl:
                    response = ydl.urlopen(url)
                    raw_bytes = response.read(MAX_SUBTITLE_BYTES + 1)
            except Exception as exc:
                logger.exception("Subtitle download failed")
                raise TranscriptExtractionError(
                    _public_yt_error(exc, "YouTube did not return the selected captions."),
                    cause=exc,
                ) from exc
            if len(raw_bytes) > MAX_SUBTITLE_BYTES:
                raise TranscriptExtractionError(
                    "The subtitle response was too large to process safely."
                )
            raw_data = raw_bytes.decode("utf-8-sig", errors="replace")
        if not isinstance(raw_data, str):
            raw_data = str(raw_data)

        extension = str(track.get("ext", "")).lower()
        try:
            if extension == "json3":
                return parse_json3(raw_data)
            if extension in {"vtt", "srt"}:
                return parse_vtt(raw_data)
        except SubtitleParseError as exc:
            raise TranscriptExtractionError(
                "The selected captions had an unsupported structure.", cause=exc
            ) from exc
        raise TranscriptExtractionError("The selected caption format is not supported.")


def validate_language(value: str) -> str:
    language = value.strip()
    if language.lower() == "auto":
        return "auto"
    if not LANGUAGE_RE.fullmatch(language):
        raise InvalidYouTubeURL("Language must be auto or a valid YouTube/BCP-47 language code.")
    return language


def _select_track(
    manual: Any,
    automatic: Any,
    requested_language: str,
) -> tuple[str | None, str | None, Mapping[str, Any] | None]:
    groups: list[tuple[str, Mapping[str, Sequence[Mapping[str, Any]]] | None]] = [
        ("manual", manual if isinstance(manual, Mapping) else None),
        ("automatic", automatic if isinstance(automatic, Mapping) else None),
    ]
    requested = requested_language.casefold().replace("_", "-")

    for source, language_map in groups:
        if not language_map:
            continue
        ranked_languages = sorted(
            ((lang, _language_score(lang, requested)) for lang in language_map),
            key=lambda item: (item[1], item[0]),
        )
        if requested != "auto":
            ranked_languages = [item for item in ranked_languages if item[1] < 100]
        else:
            ranked_languages.sort(key=lambda item: (0 if item[1] < 100 else 1, item[1], item[0]))

        for language, _score in ranked_languages:
            formats = language_map.get(language)
            if not isinstance(formats, Sequence) or isinstance(formats, (str, bytes)):
                continue
            track = _preferred_track(formats)
            if track:
                return source, str(language), track
    return None, None, None


def _language_score(language: Any, requested: str) -> int:
    value = str(language).casefold().replace("_", "-")
    if value.endswith("-orig"):
        value = value[:-5]
    if requested == "auto":
        return 0 if value == "en" else 1 if value.startswith("en-") else 100
    if value == requested:
        return 0
    requested_base = requested.split("-", 1)[0]
    value_base = value.split("-", 1)[0]
    if value == requested_base:
        return 1
    if value_base == requested_base:
        return 2
    return 100


def _preferred_track(formats: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for extension in SUBTITLE_FORMAT_PREFERENCE:
        for track in formats:
            if isinstance(track, Mapping) and str(track.get("ext", "")).lower() == extension:
                return track
    return None


def _is_normal_video_entry(info: Mapping[str, Any], url: str) -> bool:
    media_type = info.get("media_type")
    live_status = info.get("live_status")
    lowered_url = url.lower()
    if "/shorts/" in lowered_url or "/live/" in lowered_url:
        return False
    if media_type == "short" or live_status in {"is_live", "is_upcoming"}:
        return False
    return True


def _is_allowed_caption_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host == "youtube.com" or host.endswith(".youtube.com")


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _has_real_title(info: Mapping[str, Any]) -> bool:
    title = _string_value(info.get("title"))
    video_id = _string_value(info.get("id"))
    return bool(title and video_id and title.casefold() != f"youtube video #{video_id}".casefold())


def _number_value(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except TypeError, ValueError:
        return None


def _format_upload_date(value: Any) -> str | None:
    raw = _string_value(value)
    if not raw:
        return None
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def _public_yt_error(error: Exception, fallback: str) -> str:
    text = str(error).casefold()
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return "YouTube is rate-limiting this request. Wait a moment and retry."
    if "private" in text or "members-only" in text or "members only" in text:
        return "This video or channel is private or restricted."
    if "age" in text or "sign in" in text or "login" in text or "authentication" in text:
        return "This content requires YouTube authentication or is age-restricted."
    if (
        "not found" in text
        or "does not exist" in text
        or "unavailable" in text
        or "no video formats" in text
    ):
        return "This YouTube video or channel is unavailable."
    if isinstance(error, (ExtractorError, DownloadError)):
        return fallback
    return fallback

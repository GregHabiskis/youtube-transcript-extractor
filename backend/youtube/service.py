from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL
from yt_dlp.networking import Request
from yt_dlp.utils import DownloadError, ExtractorError

from backend.transcripts.cleaner import clean_cues, merge_paragraphs
from backend.transcripts.json3 import SubtitleParseError, parse_json3
from backend.transcripts.models import TranscriptBlock, TranscriptCue
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
        code: str | None = None,
        format: str | None = None,
    ) -> None:
        self.video = video
        self.source = source
        self.language = language
        self.blocks = blocks
        self.transcript = transcript
        self.status = status
        self.reason = reason
        self.code = code
        self.format = format

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
            "code": self.code,
            "format": self.format,
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

        options = self._discovery_options(latest_videos)
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
            info = self._extract_info(normalized.url, self._transcript_options())
        except YouTubeServiceError:
            raise
        except Exception as exc:
            logger.exception("Transcript extraction failed for %s", normalized.url)
            raise TranscriptExtractionError(
                _public_yt_error(exc, "Could not extract this video."),
                cause=exc,
                code="YOUTUBE_EXTRACTION_FAILED",
            ) from exc

        if not _has_real_title(info):
            raise TranscriptExtractionError(
                "This YouTube video is unavailable or restricted.",
                code="YOUTUBE_EXTRACTION_FAILED",
            )
        video = self._video_from_info(info, fallback_url=normalized.url, index=1)
        if video is None:
            raise TranscriptExtractionError(
                "YouTube returned incomplete video information.",
                code="YOUTUBE_EXTRACTION_FAILED",
            )
        manual_languages = _language_keys(info.get("subtitles"))
        automatic_languages = _language_keys(info.get("automatic_captions"))
        if not manual_languages and not automatic_languages:
            fallback_info = self._extract_caption_client_fallback(normalized.url)
            if fallback_info is not None:
                fallback_manual_languages = _language_keys(fallback_info.get("subtitles"))
                fallback_automatic_languages = _language_keys(
                    fallback_info.get("automatic_captions")
                )
                if fallback_manual_languages or fallback_automatic_languages:
                    fallback_video = self._video_from_info(
                        fallback_info, fallback_url=normalized.url, index=1
                    )
                    if fallback_video is not None:
                        info = fallback_info
                        video = fallback_video
                        manual_languages = fallback_manual_languages
                        automatic_languages = fallback_automatic_languages
        if not manual_languages and not automatic_languages:
            innertube_result = self._extract_innertube_fallback(video, language)
            if innertube_result is not None:
                return innertube_result
        if not manual_languages and not automatic_languages:
            transcript_api_result = self._extract_transcript_api_fallback(video, language)
            if transcript_api_result is not None:
                return transcript_api_result
        logger.debug(
            "yt_dlp_stage=caption_discovery video_id=%s manual_languages=%s "
            "automatic_language_count=%d automatic_sample=%s",
            video.id,
            manual_languages,
            len(automatic_languages),
            automatic_languages[:20],
        )
        source, selected_language, track = _select_track(
            info.get("subtitles"), info.get("automatic_captions"), language
        )
        logger.debug(
            "yt_dlp_stage=caption_selection video_id=%s source=%s language=%s format=%s "
            "inline_data=%s",
            video.id,
            source,
            selected_language,
            track.get("ext") if track else None,
            bool(track and track.get("data") is not None),
        )
        if not source or not selected_language or not track:
            code = _caption_unavailable_code(
                info.get("subtitles"), info.get("automatic_captions"), language
            )
            logger.debug(
                "yt_dlp_stage=caption_unavailable video_id=%s code=%s requested_language=%s",
                video.id,
                code,
                language,
            )
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
                code=code,
            )

        try:
            cues = self._download_and_parse_track(track, info)
            cleaned = clean_cues(cues)
            blocks = merge_paragraphs(cleaned)
        except TranscriptExtractionError:
            raise
        except Exception as exc:
            logger.exception("Transcript post-processing failed video_id=%s", video.id)
            raise TranscriptExtractionError(
                "The caption text could not be processed.", cause=exc, code="INTERNAL_ERROR"
            ) from exc
        logger.debug(
            "yt_dlp_stage=transcript_processed video_id=%s raw_cues=%d cleaned_cues=%d blocks=%d",
            video.id,
            len(cues),
            len(cleaned),
            len(blocks),
        )
        if not blocks:
            return TranscriptOutput(
                video=video,
                source=source,
                language=selected_language,
                blocks=[],
                transcript="",
                status="no_captions",
                reason="The caption track contained no spoken text.",
                code="NO_CAPTIONS",
                format=str(track.get("ext", "")).lower() or None,
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
            format=str(track.get("ext", "")).lower() or None,
        )

    def _extract_caption_client_fallback(self, url: str) -> Mapping[str, Any] | None:
        options = self._transcript_options()
        options["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "ios", "web_embedded"],
                "player_skip": ["webpage"],
            }
        }
        logger.debug(
            "yt_dlp_stage=caption_client_fallback_start clients=android,ios,web_embedded "
            "skip=webpage"
        )
        try:
            info = self._extract_info(url, options)
        except Exception as exc:
            logger.warning(
                "yt_dlp_stage=caption_client_fallback_failed clients=android,ios,web_embedded "
                "exception_type=%s message=%s",
                type(exc).__name__,
                _safe_error_message(exc),
            )
            return None
        logger.debug(
            "yt_dlp_stage=caption_client_fallback_ok clients=android,ios,web_embedded "
            "manual=%d automatic=%d",
            len(_language_keys(info.get("subtitles"))),
            len(_language_keys(info.get("automatic_captions"))),
        )
        return info

    @staticmethod
    def _extract_innertube_fallback(
        video: VideoMetadata, requested_language: str
    ) -> TranscriptOutput | None:
        logger.debug(
            "yt_dlp_stage=innertube_fallback_start video_id=%s requested_language=%s",
            video.id,
            requested_language,
        )
        try:
            response = requests.post(
                "https://www.youtube.com/youtubei/v1/player",
                headers={"Accept-Language": "en-US", "Content-Type": "application/json"},
                json={
                    "context": {
                        "client": {"clientName": "ANDROID", "clientVersion": "20.10.38"}
                    },
                    "videoId": video.id,
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            tracks = (
                payload.get("captions", {})
                .get("playerCaptionsTracklistRenderer", {})
                .get("captionTracks", [])
            )
            if not isinstance(tracks, Sequence) or isinstance(tracks, (str, bytes)):
                return None
            selected = _select_innertube_track(tracks, requested_language)
            if selected is None:
                logger.debug(
                    "yt_dlp_stage=innertube_fallback_no_track video_id=%s available=%d",
                    video.id,
                    len(tracks),
                )
                return None
            caption_url = _json3_caption_url(selected.get("baseUrl"))
            if caption_url is None:
                return None
            caption_response = requests.get(caption_url, timeout=20)
            caption_response.raise_for_status()
            if len(caption_response.content) > MAX_SUBTITLE_BYTES:
                return None
            raw_data = caption_response.content.decode("utf-8-sig", errors="replace")
            try:
                cues = parse_json3(raw_data)
            except SubtitleParseError:
                cues = parse_vtt(raw_data)
            cleaned = clean_cues(cues)
            blocks = merge_paragraphs(cleaned)
            if not blocks:
                return None
            source = "automatic" if str(selected.get("kind", "")).casefold() == "asr" else "manual"
            language = str(selected.get("languageCode", ""))
            transcript = render_plaintext(
                title=video.title,
                channel=video.channel,
                url=video.url,
                upload_date=video.upload_date,
                source=source,
                language=language,
                blocks=blocks,
            )
            logger.debug(
                "yt_dlp_stage=innertube_fallback_ok video_id=%s source=%s language=%s "
                "cues=%d blocks=%d",
                video.id,
                source,
                language,
                len(cues),
                len(blocks),
            )
            return TranscriptOutput(
                video=video,
                source=source,
                language=language,
                blocks=blocks,
                transcript=transcript,
                format="json3",
            )
        except Exception as exc:
            logger.warning(
                "yt_dlp_stage=innertube_fallback_failed video_id=%s exception_type=%s message=%s",
                video.id,
                type(exc).__name__,
                _safe_error_message(exc),
            )
            return None

    @staticmethod
    def _extract_transcript_api_fallback(
        video: VideoMetadata, requested_language: str
    ) -> TranscriptOutput | None:
        logger.debug(
            "yt_dlp_stage=transcript_api_fallback_start video_id=%s requested_language=%s",
            video.id,
            requested_language,
        )
        try:
            transcript_list = list(YouTubeTranscriptApi().list(video.id))
            selected = _select_transcript_api_track(transcript_list, requested_language)
            if selected is None:
                logger.debug(
                    "yt_dlp_stage=transcript_api_fallback_no_track video_id=%s available=%d",
                    video.id,
                    len(transcript_list),
                )
                return None
            snippets = selected.fetch()
            cues = _transcript_api_cues(snippets)
            cleaned = clean_cues(cues)
            blocks = merge_paragraphs(cleaned)
            if not blocks:
                return None
            source = "automatic" if bool(selected.is_generated) else "manual"
            language = str(selected.language_code)
            transcript = render_plaintext(
                title=video.title,
                channel=video.channel,
                url=video.url,
                upload_date=video.upload_date,
                source=source,
                language=language,
                blocks=blocks,
            )
            logger.debug(
                "yt_dlp_stage=transcript_api_fallback_ok video_id=%s source=%s "
                "language=%s cues=%d blocks=%d",
                video.id,
                source,
                language,
                len(cues),
                len(blocks),
            )
            return TranscriptOutput(
                video=video,
                source=source,
                language=language,
                blocks=blocks,
                transcript=transcript,
            )
        except Exception as exc:
            logger.warning(
                "yt_dlp_stage=transcript_api_fallback_failed video_id=%s "
                "exception_type=%s message=%s",
                video.id,
                type(exc).__name__,
                _safe_error_message(exc),
            )
            return None

    def _extract_info(
        self, url: str, extra_options: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        options = self._base_options()
        if extra_options:
            options.update(extra_options)
        mode = (
            "transcript"
            if extra_options and extra_options.get("writesubtitles")
            else "discovery"
            if extra_options and extra_options.get("extract_flat")
            else "metadata"
        )
        logger.debug(
            "yt_dlp_stage=metadata_start mode=%s extract_flat=%s skip_download=%s",
            mode,
            bool(options.get("extract_flat")),
            bool(options.get("skip_download")),
        )
        with YoutubeDL(options) as ydl:
            result = ydl.extract_info(url, download=False)
        if not isinstance(result, Mapping):
            raise YouTubeServiceError("yt-dlp returned no video information.")
        logger.debug(
            "yt_dlp_stage=metadata_ok mode=%s video_id=%s title_present=%s",
            mode,
            result.get("id"),
            bool(_string_value(result.get("title"))),
        )
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
    def _discovery_options(latest_videos: int) -> dict[str, Any]:
        options = YouTubeService._base_options()
        options.update(
            {
                "extract_flat": True,
                "lazy_playlist": True,
                "playlist_items": f"1:{latest_videos}",
                "noplaylist": False,
                "ignoreerrors": True,
            }
        )
        return options

    @staticmethod
    def _transcript_options() -> dict[str, Any]:
        options = YouTubeService._base_options()
        options.update(
            {
                "noplaylist": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitlesformat": "json3/vtt/srt",
                "ignore_no_formats_error": True,
            }
        )
        return options

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
        extension = str(track.get("ext", "")).lower()
        raw_data = track.get("data")
        if raw_data is None:
            url = track.get("url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                raise TranscriptExtractionError(
                    "yt-dlp returned an invalid subtitle URL.", code="SUBTITLE_ACCESS_FAILED"
                )
            if not _is_allowed_caption_url(url):
                raise TranscriptExtractionError(
                    "yt-dlp returned a caption URL outside YouTube.",
                    code="SUBTITLE_ACCESS_FAILED",
                )
            options = YouTubeService._base_options()
            headers: dict[str, str] = {}
            for header_group in (info.get("http_headers"), track.get("http_headers")):
                if isinstance(header_group, Mapping):
                    headers.update(
                        {
                            str(name): str(value)
                            for name, value in header_group.items()
                            if value is not None
                        }
                    )
            try:
                with YoutubeDL(options) as ydl:
                    response = ydl.urlopen(Request(url, headers=headers))
                    try:
                        raw_bytes = response.read(MAX_SUBTITLE_BYTES + 1)
                    finally:
                        with suppress(Exception):
                            response.close()
            except Exception as exc:
                logger.error(
                    "yt_dlp_stage=subtitle_download_failed video_id=%s format=%s "
                    "exception_type=%s message=%s",
                    info.get("id"),
                    extension,
                    type(exc).__name__,
                    _safe_error_message(exc),
                )
                raise TranscriptExtractionError(
                    _public_yt_error(exc, "YouTube did not return the selected captions."),
                    cause=exc,
                    code="SUBTITLE_DOWNLOAD_FAILED",
                ) from exc
            if isinstance(raw_bytes, str):
                raw_bytes = raw_bytes.encode("utf-8")
            if not isinstance(raw_bytes, bytes):
                raise TranscriptExtractionError(
                    "YouTube returned an invalid subtitle response.",
                    code="SUBTITLE_DOWNLOAD_FAILED",
                )
            if len(raw_bytes) > MAX_SUBTITLE_BYTES:
                raise TranscriptExtractionError(
                    "The subtitle response was too large to process safely.",
                    code="SUBTITLE_DOWNLOAD_FAILED",
                )
            raw_data = raw_bytes.decode("utf-8-sig", errors="replace")
        elif isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8-sig", errors="replace")
        elif not isinstance(raw_data, str):
            raw_data = str(raw_data)

        raw_size = len(raw_data.encode("utf-8"))
        if raw_size > MAX_SUBTITLE_BYTES:
            raise TranscriptExtractionError(
                "The subtitle response was too large to process safely.",
                code="SUBTITLE_DOWNLOAD_FAILED",
            )
        logger.debug(
            "yt_dlp_stage=subtitle_retrieved video_id=%s format=%s bytes=%d retrieval=%s",
            info.get("id"),
            extension,
            raw_size,
            "inline" if track.get("data") is not None else "url",
        )
        try:
            if extension == "json3":
                cues = parse_json3(raw_data)
            elif extension in {"vtt", "srt"}:
                cues = parse_vtt(raw_data)
            else:
                raise TranscriptExtractionError(
                    "The selected caption format is not supported.",
                    code="SUBTITLE_PARSE_FAILED",
                )
        except SubtitleParseError as exc:
            logger.error(
                "yt_dlp_stage=subtitle_parse_failed video_id=%s format=%s "
                "exception_type=%s message=%s",
                info.get("id"),
                extension,
                type(exc).__name__,
                _safe_error_message(exc),
            )
            raise TranscriptExtractionError(
                "The selected captions had an unsupported structure.",
                cause=exc,
                code="SUBTITLE_PARSE_FAILED",
            ) from exc
        if not cues and raw_data.strip():
            raise TranscriptExtractionError(
                "The selected captions had no parseable cues.", code="SUBTITLE_PARSE_FAILED"
            )
        logger.debug(
            "yt_dlp_stage=subtitle_parsed video_id=%s format=%s cues=%d",
            info.get("id"),
            extension,
            len(cues),
        )
        return cues


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


def _select_transcript_api_track(
    transcripts: Sequence[Any], requested_language: str
) -> Any | None:
    requested = requested_language.casefold().replace("_", "-")
    for is_generated in (False, True):
        candidates = [
            transcript
            for transcript in transcripts
            if bool(getattr(transcript, "is_generated", False)) is is_generated
        ]
        ranked = sorted(
            candidates,
            key=lambda transcript: (
                _language_score(getattr(transcript, "language_code", ""), requested),
                str(getattr(transcript, "language_code", "")),
            ),
        )
        if requested != "auto":
            ranked = [
                transcript
                for transcript in ranked
                if _language_score(getattr(transcript, "language_code", ""), requested) < 100
            ]
        if ranked:
            return ranked[0]
    return None


def _select_innertube_track(
    tracks: Sequence[Any], requested_language: str
) -> Mapping[str, Any] | None:
    requested = requested_language.casefold().replace("_", "-")
    for is_generated in (False, True):
        candidates = [
            track
            for track in tracks
            if isinstance(track, Mapping)
            and (str(track.get("kind", "")).casefold() == "asr") is is_generated
        ]
        ranked = sorted(
            candidates,
            key=lambda track: (
                _language_score(track.get("languageCode", ""), requested),
                str(track.get("languageCode", "")),
            ),
        )
        if requested != "auto":
            ranked = [
                track
                for track in ranked
                if _language_score(track.get("languageCode", ""), requested) < 100
            ]
        if ranked:
            return ranked[0]
    return None


def _json3_caption_url(value: Any) -> str | None:
    if not isinstance(value, str) or not _is_allowed_caption_url(value):
        return None
    parts = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key != "fmt"
    ]
    query.append(("fmt", "json3"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _transcript_api_cues(snippets: Sequence[Any]) -> list[TranscriptCue]:
    cues: list[TranscriptCue] = []
    for snippet in snippets:
        if isinstance(snippet, Mapping):
            text = _string_value(snippet.get("text"))
            start_seconds = _number_value(snippet.get("start"))
            duration_seconds = _number_value(snippet.get("duration"))
        else:
            text = _string_value(getattr(snippet, "text", None))
            start_seconds = _number_value(getattr(snippet, "start", None))
            duration_seconds = _number_value(getattr(snippet, "duration", None))
        if not text or start_seconds is None or duration_seconds is None:
            continue
        if not math.isfinite(start_seconds) or not math.isfinite(duration_seconds):
            continue
        start_ms = max(0, round(start_seconds * 1000))
        end_ms = max(start_ms + 1, round((start_seconds + max(0, duration_seconds)) * 1000))
        cues.append(TranscriptCue(start_ms=start_ms, end_ms=end_ms, text=text))
    return cues


def _language_keys(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    return sorted(str(language) for language in value)


def _caption_unavailable_code(manual: Any, automatic: Any, requested_language: str) -> str:
    manual_map = manual if isinstance(manual, Mapping) else {}
    automatic_map = automatic if isinstance(automatic, Mapping) else {}
    if not manual_map and not automatic_map:
        return "NO_CAPTIONS"
    if requested_language == "auto":
        return "SUBTITLE_ACCESS_FAILED"
    requested = requested_language.casefold().replace("_", "-")
    for language_map in (manual_map, automatic_map):
        for language, _formats in language_map.items():
            if _language_score(language, requested) < 100:
                return "SUBTITLE_ACCESS_FAILED"
    return "LANGUAGE_UNAVAILABLE"


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
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return (
        host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtube-nocookie.com"
        or host.endswith(".youtube-nocookie.com")
        or host == "googlevideo.com"
        or host.endswith(".googlevideo.com")
    )


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


def _safe_error_message(error: Exception) -> str:
    """Keep diagnostic messages useful without logging signed caption URLs."""

    message = str(error)
    if "?" in message:
        message = message.split("?", 1)[0] + "?…"
    return message[:500]

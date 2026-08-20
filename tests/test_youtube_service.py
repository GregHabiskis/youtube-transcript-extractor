from __future__ import annotations

import json

import pytest
from yt_dlp.networking import Request

from backend.youtube.errors import TranscriptExtractionError
from backend.youtube.service import YouTubeService, _select_track


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, _size: int = -1) -> bytes:
        return self.data

    def close(self) -> None:
        return None


class FakeYoutubeDL:
    instances = []

    def __init__(self, options):
        self.options = options
        self.info_calls = []
        self.urlopen_calls = []
        FakeYoutubeDL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, url, download=False):
        self.info_calls.append((url, download))
        if "/videos" in url:
            return {
                "channel": "Example Channel",
                "channel_url": "https://www.youtube.com/@ExampleChannel",
                "entries": [
                    {
                        "id": "BaW_jenozKc",
                        "title": "Newest",
                        "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
                        "channel": "Example Channel",
                        "duration": 10,
                        "thumbnail": "https://i.ytimg.com/vi/BaW_jenozKc/hqdefault.jpg",
                        "media_type": "video",
                    },
                    {
                        "id": "dQw4w9WgXcQ",
                        "title": "Short that must be skipped",
                        "url": "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                        "media_type": "short",
                    },
                ],
            }
        return {
            "id": "BaW_jenozKc",
            "title": "Newest",
            "channel": "Example Channel",
            "channel_url": "https://www.youtube.com/@ExampleChannel",
            "upload_date": "20260120",
            "duration": 10,
            "subtitles": {
                "en": [
                    {
                        "ext": "json3",
                        "data": json.dumps(
                            {
                                "events": [
                                    {
                                        "tStartMs": 0,
                                        "dDurationMs": 1000,
                                        "segs": [{"utf8": "hello"}],
                                    }
                                ]
                            }
                        ),
                    }
                ],
            },
            "automatic_captions": {
                "en": [
                    {
                        "ext": "json3",
                        "data": json.dumps(
                            {
                                "events": [
                                    {
                                        "tStartMs": 0,
                                        "dDurationMs": 1000,
                                        "segs": [{"utf8": "automatic"}],
                                    }
                                ]
                            }
                        ),
                    }
                ],
            },
        }

    def urlopen(self, request):
        self.urlopen_calls.append(request)
        return FakeResponse(b"")


def test_service_bounds_channel_discovery_and_never_downloads_media(monkeypatch):
    FakeYoutubeDL.instances.clear()
    monkeypatch.setattr("backend.youtube.service.YoutubeDL", FakeYoutubeDL)
    result = YouTubeService().inspect("https://www.youtube.com/@ExampleChannel", 10)
    assert [video.id for video in result.videos] == ["BaW_jenozKc"]
    instance = FakeYoutubeDL.instances[0]
    assert instance.options["playlist_items"] == "1:10"
    assert instance.options["extract_flat"] is True
    assert instance.options["skip_download"] is True
    assert instance.info_calls[0][1] is False


def test_service_prefers_manual_captions(monkeypatch):
    FakeYoutubeDL.instances.clear()
    monkeypatch.setattr("backend.youtube.service.YoutubeDL", FakeYoutubeDL)
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert result.status == "complete"
    assert result.source == "manual"
    assert result.language == "en"
    assert result.format == "json3"
    assert "hello" in result.transcript
    assert all(instance.options["skip_download"] for instance in FakeYoutubeDL.instances)
    assert all("extract_flat" not in instance.options for instance in FakeYoutubeDL.instances)
    assert all("proxy" not in instance.options for instance in FakeYoutubeDL.instances)


def test_service_falls_back_to_automatic_captions(monkeypatch):
    class AutomaticOnlyYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {
                "id": "BaW_jenozKc",
                "title": "Automatic only",
                "channel": "Example Channel",
                "automatic_captions": {
                    "en": [
                        {
                            "ext": "json3",
                            "data": json.dumps(
                                {
                                    "events": [
                                        {
                                            "tStartMs": 0,
                                            "dDurationMs": 1000,
                                            "segs": [{"utf8": "automatic words"}],
                                        }
                                    ]
                                }
                            ),
                        }
                    ]
                },
            }

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", AutomaticOnlyYoutubeDL)
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert result.status == "complete"
    assert result.source == "automatic"
    assert result.format == "json3"
    assert "automatic words" in result.transcript


def test_service_matches_english_variant_and_preserves_manual_priority(monkeypatch):
    class VariantYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {
                "id": "BaW_jenozKc",
                "title": "English variant",
                "subtitles": {
                    "en-US": [
                        {
                            "ext": "json3",
                            "data": json.dumps(
                                {
                                    "events": [
                                        {
                                            "tStartMs": 0,
                                            "dDurationMs": 1000,
                                            "segs": [{"utf8": "variant words"}],
                                        }
                                    ]
                                }
                            ),
                        }
                    ]
                },
                "automatic_captions": {
                    "en": [
                        {
                            "ext": "json3",
                            "data": json.dumps(
                                {
                                    "events": [
                                        {
                                            "tStartMs": 0,
                                            "dDurationMs": 1000,
                                            "segs": [{"utf8": "automatic words"}],
                                        }
                                    ]
                                }
                            ),
                        }
                    ]
                },
            }

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", VariantYoutubeDL)
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert result.source == "manual"
    assert result.language == "en-US"
    assert "variant words" in result.transcript


def test_auto_language_prefers_a_usable_manual_english_variant():
    source, language, track = _select_track(
        {"en-US": [{"ext": "vtt", "data": "WEBVTT"}]},
        {"en": [{"ext": "json3", "data": "{}"}]},
        "auto",
    )
    assert source == "manual"
    assert language == "en-US"
    assert track is not None
    assert track["ext"] == "vtt"


def test_service_falls_back_to_vtt_for_automatic_captions(monkeypatch):
    class VttYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {
                "id": "BaW_jenozKc",
                "title": "VTT fallback",
                "automatic_captions": {
                    "en": [
                        {
                            "ext": "vtt",
                            "data": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello VTT\n",
                        }
                    ]
                },
            }

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", VttYoutubeDL)
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert result.source == "automatic"
    assert result.language == "en"
    assert result.format == "vtt"
    assert "Hello VTT" in result.transcript


def test_service_reports_true_no_caption_case(monkeypatch):
    class NoCaptionYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {"id": "BaW_jenozKc", "title": "No captions"}

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", NoCaptionYoutubeDL)
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert result.status == "no_captions"
    assert result.code == "NO_CAPTIONS"
    assert result.reason == "No captions are available for this video."


def test_direct_failure_without_proxy_returns_blocked_error(monkeypatch):
    class BlockedYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            raise RuntimeError("HTTP Error 429: Sign in to confirm you are not a bot")

    monkeypatch.delenv("YTDLP_PROXY_URL", raising=False)
    monkeypatch.setattr("backend.youtube.service.YoutubeDL", BlockedYoutubeDL)

    with pytest.raises(
        TranscriptExtractionError, match="YouTube blocked transcript retrieval"
    ) as error:
        YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert error.value.code == "YOUTUBE_BLOCKED"


def test_direct_failure_retries_once_through_proxy(monkeypatch):
    class DirectThenProxyYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            if self.options.get("proxy") is None:
                raise RuntimeError("HTTP Error 429: Sign in to confirm you are not a bot")
            return {
                "id": "BaW_jenozKc",
                "title": "Proxy success",
                "channel": "Example Channel",
                "subtitles": {
                    "en": [
                        {
                            "ext": "json3",
                            "data": json.dumps(
                                {
                                    "events": [
                                        {
                                            "tStartMs": 0,
                                            "dDurationMs": 1000,
                                            "segs": [{"utf8": "proxy words"}],
                                        }
                                    ]
                                }
                            ),
                        }
                    ]
                },
            }

    monkeypatch.setenv("YTDLP_PROXY_URL", "https://user:secret@example-proxy.test:8443")
    monkeypatch.setattr("backend.youtube.service.YoutubeDL", DirectThenProxyYoutubeDL)
    FakeYoutubeDL.instances.clear()
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")

    assert result.status == "complete"
    assert "proxy words" in result.transcript
    assert len(DirectThenProxyYoutubeDL.instances) == 2
    assert DirectThenProxyYoutubeDL.instances[0].options.get("proxy") is None
    assert DirectThenProxyYoutubeDL.instances[1].options["proxy"] == (
        "https://user:secret@example-proxy.test:8443"
    )


def test_direct_failure_proxy_retry_failure_is_structured(monkeypatch):
    class AlwaysBlockedYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setenv("YTDLP_PROXY_URL", "https://user:secret@example-proxy.test:8443")
    monkeypatch.setattr("backend.youtube.service.YoutubeDL", AlwaysBlockedYoutubeDL)

    with pytest.raises(
        TranscriptExtractionError,
        match="Transcript retrieval failed through the configured proxy",
    ) as error:
        YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert error.value.code == "PROXY_RETRY_FAILED"
    assert "secret" not in error.value.public_message


def test_genuine_no_captions_does_not_trigger_proxy(monkeypatch):
    class NoCaptionYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {"id": "BaW_jenozKc", "title": "No captions"}

    monkeypatch.setenv("YTDLP_PROXY_URL", "https://user:secret@example-proxy.test:8443")
    monkeypatch.setattr("backend.youtube.service.YoutubeDL", NoCaptionYoutubeDL)
    FakeYoutubeDL.instances.clear()
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")

    assert result.status == "no_captions"
    assert result.code == "NO_CAPTIONS"
    assert len(NoCaptionYoutubeDL.instances) == 1


def test_proxy_credentials_are_not_exposed_in_error_response(monkeypatch, caplog):
    class BlockedYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            raise RuntimeError(
                "HTTP Error 403: proxy request failed for https://user:secret@example-proxy.test"
            )

    proxy_url = "https://user:secret@example-proxy.test:8443"
    monkeypatch.setenv("YTDLP_PROXY_URL", proxy_url)
    monkeypatch.setattr("backend.youtube.service.YoutubeDL", BlockedYoutubeDL)

    with pytest.raises(TranscriptExtractionError) as error:
        YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert proxy_url not in error.value.public_message
    assert "secret" not in error.value.public_message
    assert proxy_url not in caplog.text
    assert "secret" not in caplog.text


def test_service_distinguishes_missing_requested_language(monkeypatch):
    class SpanishOnlyYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {
                "id": "BaW_jenozKc",
                "title": "Spanish only",
                "subtitles": {"es": [{"ext": "vtt", "data": "WEBVTT"}]},
            }

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", SpanishOnlyYoutubeDL)
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert result.status == "no_captions"
    assert result.code == "LANGUAGE_UNAVAILABLE"


def test_service_reports_subtitle_download_failures(monkeypatch):
    class DownloadFailureYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {
                "id": "BaW_jenozKc",
                "title": "Download failure",
                "http_headers": {"User-Agent": "test-agent"},
                "subtitles": {
                    "en": [
                        {
                            "ext": "vtt",
                            "url": "https://www.youtube.com/api/timedtext?v=BaW_jenozKc",
                            "http_headers": {"X-Test": "track"},
                        }
                    ]
                },
            }

        def urlopen(self, request):
            self.urlopen_calls.append(request)
            raise OSError("caption server returned 403")

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", DownloadFailureYoutubeDL)
    with pytest.raises(TranscriptExtractionError, match="YouTube did not return") as error:
        YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert error.value.code == "SUBTITLE_DOWNLOAD_FAILED"


def test_service_reports_subtitle_parse_failures(monkeypatch):
    class ParseFailureYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {
                "id": "BaW_jenozKc",
                "title": "Parse failure",
                "subtitles": {"en": [{"ext": "json3", "data": "not json"}]},
            }

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", ParseFailureYoutubeDL)
    with pytest.raises(TranscriptExtractionError) as error:
        YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    assert error.value.code == "SUBTITLE_PARSE_FAILED"


def test_service_uses_yt_dlp_request_and_track_headers(monkeypatch):
    class HeaderYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download=False):
            self.info_calls.append((url, download))
            return {
                "id": "BaW_jenozKc",
                "title": "Header request",
                "http_headers": {"User-Agent": "metadata-agent"},
                "subtitles": {
                    "en": [
                        {
                            "ext": "vtt",
                            "url": "https://www.youtube.com/api/timedtext?v=BaW_jenozKc",
                            "http_headers": {"X-Track": "track-value"},
                        }
                    ]
                },
            }

        def urlopen(self, request):
            self.urlopen_calls.append(request)
            return FakeResponse(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHeaders ok\n")

    monkeypatch.setattr("backend.youtube.service.YoutubeDL", HeaderYoutubeDL)
    HeaderYoutubeDL.instances.clear()
    result = YouTubeService().extract_transcript("https://youtu.be/BaW_jenozKc", "en")
    request = next(
        call for instance in HeaderYoutubeDL.instances for call in instance.urlopen_calls
    )
    assert isinstance(request, Request)
    assert request.headers["User-Agent"] == "metadata-agent"
    assert request.headers["X-Track"] == "track-value"
    assert "Headers ok" in result.transcript

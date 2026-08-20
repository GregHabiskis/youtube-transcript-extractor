from __future__ import annotations

import json

from backend.youtube.service import YouTubeService


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, _size: int = -1) -> bytes:
        return self.data


class FakeYoutubeDL:
    instances = []

    def __init__(self, options):
        self.options = options
        self.info_calls = []
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

    def urlopen(self, _url):
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
    assert "hello" in result.transcript
    assert all(instance.options["skip_download"] for instance in FakeYoutubeDL.instances)


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
    assert "automatic words" in result.transcript

import pytest

from backend.youtube.errors import InvalidYouTubeURL
from backend.youtube.urls import normalize_youtube_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://www.youtube.com/@ExampleChannel",
            "https://www.youtube.com/@ExampleChannel/videos",
        ),
        (
            "https://www.youtube.com/@ExampleChannel/videos",
            "https://www.youtube.com/@ExampleChannel/videos",
        ),
        (
            "https://youtube.com/channel/UC1234567890/videos?view=0",
            "https://www.youtube.com/channel/UC1234567890/videos",
        ),
    ],
)
def test_channel_urls_normalize_to_videos(raw: str, expected: str):
    normalized = normalize_youtube_url(raw)
    assert normalized.kind == "channel"
    assert normalized.url == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.youtube.com/watch?v=BaW_jenozKc&feature=share",
        "https://youtu.be/BaW_jenozKc?t=12",
        "https://www.youtube.com/shorts/BaW_jenozKc",
    ],
)
def test_video_urls_are_canonicalized(raw: str):
    normalized = normalize_youtube_url(raw)
    assert normalized.kind == "video"
    assert normalized.video_id == "BaW_jenozKc"
    assert normalized.url == "https://www.youtube.com/watch?v=BaW_jenozKc"


@pytest.mark.parametrize(
    "raw",
    [
        "https://example.com/watch?v=BaW_jenozKc",
        "https://www.youtube.com/@ExampleChannel/shorts",
        "https://www.youtube.com/playlist?list=PL123",
        "not a url",
    ],
)
def test_unrelated_or_unsupported_urls_are_rejected(raw: str):
    with pytest.raises(InvalidYouTubeURL):
        normalize_youtube_url(raw)

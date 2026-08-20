from backend.transcripts.export import sanitize_filename, transcript_filename
from backend.transcripts.models import TranscriptBlock
from backend.transcripts.renderer import format_timestamp, render_plaintext


def test_hour_long_timestamp_format():
    assert format_timestamp(3_723_456) == "01:02:03.456"
    assert format_timestamp(360_000_000) == "100:00:00.000"


def test_plaintext_renderer_keeps_metadata_and_timing():
    output = render_plaintext(
        title="A title",
        channel="A channel",
        url="https://www.youtube.com/watch?v=BaW_jenozKc",
        upload_date="2026-01-20",
        source="manual",
        language="en-US",
        blocks=[TranscriptBlock(0, 6420, "Welcome back.")],
    )
    assert "Title: A title" in output
    assert "Caption source: Manual" in output
    assert "[00:00:00.000 --> 00:00:06.420]" in output
    assert output.endswith("\n")


def test_filename_sanitization_is_cross_platform():
    assert sanitize_filename("A / dangerous: title?.txt") == "A dangerous title .txt"
    assert sanitize_filename("CON") == "transcript-con"
    assert "../" not in transcript_filename(3, "../escape")
    assert transcript_filename(3, "Episode") == "003-Episode.txt"

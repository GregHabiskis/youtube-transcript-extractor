from backend.transcripts.json3 import parse_json3
from backend.transcripts.vtt import parse_timestamp, parse_vtt


def test_json3_parser_combines_segments_and_preserves_timing():
    payload = (
        '{"events":[{"tStartMs":1000,"dDurationMs":2500,"segs":'
        '[{"utf8":"Hello "},{"utf8":"world"}]},{"tStartMs":4000,'
        '"segs":[{"utf8":"Next"}]}]}'
    )
    cues = parse_json3(payload)
    assert cues[0].start_ms == 1000
    assert cues[0].end_ms == 3500
    assert cues[0].text == "Hello world"
    assert cues[1].end_ms == 5000


def test_vtt_parser_skips_metadata_and_handles_tags_for_cleaner():
    payload = """WEBVTT

NOTE
generated metadata

cue-1
01:02:03.400 --> 01:02:08.900 align:start
<c.colorE5E5E5>Hello &amp; welcome</c>

"""
    cues = parse_vtt(payload)
    assert len(cues) == 1
    assert cues[0].start_ms == 3_723_400
    assert cues[0].end_ms == 3_728_900
    assert cues[0].text == "<c.colorE5E5E5>Hello &amp; welcome</c>"


def test_vtt_timestamp_supports_hours_and_comma_milliseconds():
    assert parse_timestamp("12:34:56,789") == 45_296_789

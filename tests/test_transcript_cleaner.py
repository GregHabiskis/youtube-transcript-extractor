from backend.transcripts.cleaner import clean_cues, merge_paragraphs
from backend.transcripts.models import TranscriptCue


def logical_text(cues):
    return " ".join(cue.text for cue in cues)


def test_exact_duplicate_cues_are_collapsed_and_timing_is_extended():
    cues = clean_cues(
        [
            TranscriptCue(0, 1000, "hello everyone"),
            TranscriptCue(1000, 2200, "hello everyone"),
        ]
    )
    assert logical_text(cues) == "hello everyone"
    assert cues[0].start_ms == 0
    assert cues[0].end_ms == 2200


def test_rolling_caption_repetition_is_removed():
    cues = clean_cues(
        [
            TranscriptCue(0, 1800, "today we're going"),
            TranscriptCue(1000, 2800, "today we're going to talk"),
            TranscriptCue(2000, 4000, "we're going to talk about Python"),
        ]
    )
    assert logical_text(cues) == "today we're going to talk about Python"


def test_legitimate_repeated_words_inside_a_cue_are_preserved():
    cues = clean_cues([TranscriptCue(0, 1500, "very very important")])
    assert logical_text(cues) == "very very important"


def test_overlapping_cues_do_not_repeat_their_shared_suffix_prefix():
    cues = clean_cues(
        [
            TranscriptCue(0, 1800, "this is how Python works"),
            TranscriptCue(1200, 3000, "Python works when the interpreter"),
            TranscriptCue(2400, 4200, "when the interpreter executes the code"),
        ]
    )
    assert logical_text(cues) == "this is how Python works when the interpreter executes the code"


def test_markup_entities_and_whitespace_are_normalized():
    cues = clean_cues([TranscriptCue(0, 1000, "  Hello&nbsp; <b>world</b>\nagain  ")])
    assert cues[0].text == "Hello world again"


def test_paragraph_merge_preserves_earliest_start_and_latest_end():
    blocks = merge_paragraphs(
        [
            TranscriptCue(1000, 2000, "Welcome back."),
            TranscriptCue(2200, 4000, "Today we build a transcript."),
        ]
    )
    assert len(blocks) == 2
    blocks = merge_paragraphs(
        [
            TranscriptCue(1000, 2000, "Welcome back today"),
            TranscriptCue(2200, 4000, "we are testing timestamps"),
        ]
    )
    assert len(blocks) == 1
    assert blocks[0].start_ms == 1000
    assert blocks[0].end_ms == 4000

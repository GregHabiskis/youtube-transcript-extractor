from __future__ import annotations

import re
from dataclasses import replace

from .models import TranscriptBlock, TranscriptCue
from .normalizer import normalize_caption_text

WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
MAX_OVERLAP_WORDS = 40
OVERLAP_MIN_WORDS = 2
ROLLING_GAP_MS = 1250
MAX_PARAGRAPH_CHARS = 480
MAX_PARAGRAPH_DURATION_MS = 45_000


def clean_cues(cues: list[TranscriptCue]) -> list[TranscriptCue]:
    """Remove rolling-caption duplication while retaining cue timing.

    Auto captions frequently expose a growing window of speech. The algorithm
    compares the current cue's word prefix with the accepted transcript suffix
    and removes only a conservative overlap of two or more words. A short
    temporal relationship is required for non-identical overlaps, which avoids
    treating ordinary repeated phrases in separate speech as caption artifacts.
    """

    accepted_words: list[str] = []
    cleaned: list[TranscriptCue] = []
    previous_raw: TranscriptCue | None = None

    for cue in cues:
        text = normalize_caption_text(cue.text)
        if not text:
            previous_raw = cue
            continue

        normalized_words = text.split()
        if not normalized_words:
            previous_raw = cue
            continue

        if cleaned and _same_words(cleaned[-1].text, text):
            cleaned[-1] = replace(cleaned[-1], end_ms=max(cleaned[-1].end_ms, cue.end_ms))
            previous_raw = cue
            continue

        overlap = _find_overlap(accepted_words, normalized_words)
        related = previous_raw is None or cue.start_ms <= previous_raw.end_ms + ROLLING_GAP_MS
        if overlap >= OVERLAP_MIN_WORDS and related:
            remaining = normalized_words[overlap:]
            if not remaining:
                if cleaned:
                    cleaned[-1] = replace(cleaned[-1], end_ms=max(cleaned[-1].end_ms, cue.end_ms))
                previous_raw = cue
                continue
            text = " ".join(remaining)
            normalized_words = remaining

        cleaned.append(TranscriptCue(start_ms=cue.start_ms, end_ms=cue.end_ms, text=text))
        accepted_words.extend(normalized_words)
        if len(accepted_words) > MAX_OVERLAP_WORDS:
            accepted_words = accepted_words[-MAX_OVERLAP_WORDS:]
        previous_raw = cue

    return cleaned


def merge_paragraphs(
    cues: list[TranscriptCue],
    *,
    max_gap_ms: int = 1250,
    max_chars: int = MAX_PARAGRAPH_CHARS,
    max_duration_ms: int = MAX_PARAGRAPH_DURATION_MS,
) -> list[TranscriptBlock]:
    """Merge nearby cue fragments into bounded, readable timestamped blocks."""

    blocks: list[TranscriptBlock] = []
    for cue in cues:
        if not cue.text.strip():
            continue
        if not blocks:
            blocks.append(TranscriptBlock(cue.start_ms, cue.end_ms, cue.text.strip()))
            continue

        current = blocks[-1]
        gap_ms = cue.start_ms - current.end_ms
        candidate_text = f"{current.text} {cue.text.strip()}".strip()
        can_merge = (
            gap_ms <= max_gap_ms
            and len(candidate_text) <= max_chars
            and cue.end_ms - current.start_ms <= max_duration_ms
            and _looks_like_continuation(current.text, cue.text)
        )
        if can_merge:
            blocks[-1] = TranscriptBlock(
                start_ms=min(current.start_ms, cue.start_ms),
                end_ms=max(current.end_ms, cue.end_ms),
                text=candidate_text,
            )
        else:
            blocks.append(TranscriptBlock(cue.start_ms, cue.end_ms, cue.text.strip()))
    return blocks


def _find_overlap(previous_words: list[str], current_words: list[str]) -> int:
    if not previous_words or not current_words:
        return 0
    previous = previous_words[-MAX_OVERLAP_WORDS:]
    maximum = min(len(previous), len(current_words))
    for size in range(maximum, OVERLAP_MIN_WORDS - 1, -1):
        if [_comparison_word(word) for word in previous[-size:]] == [
            _comparison_word(word) for word in current_words[:size]
        ]:
            return size
    return 0


def _same_words(left: str, right: str) -> bool:
    return [_comparison_word(word) for word in left.split()] == [
        _comparison_word(word) for word in right.split()
    ]


def _comparison_word(word: str) -> str:
    return "".join(char for char in word.casefold() if char.isalnum() or char in "'’")


def _looks_like_continuation(previous: str, current: str) -> bool:
    if previous.rstrip().endswith((".", "!", "?", "。", "！", "？")):
        stripped = current.lstrip()
        return bool(stripped) and (stripped[0].islower() or stripped[0] in ",;:)]")
    return True

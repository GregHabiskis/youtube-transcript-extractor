from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranscriptCue:
    """A single timed caption cue in milliseconds."""

    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptBlock:
    """A readable paragraph formed from one or more cleaned cues."""

    start_ms: int
    end_ms: int
    text: str

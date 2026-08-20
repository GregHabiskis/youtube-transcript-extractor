from __future__ import annotations

import json
from typing import Any

from .models import TranscriptCue


class SubtitleParseError(ValueError):
    """Raised when a supported subtitle payload cannot be parsed."""


def parse_json3(payload: str) -> list[TranscriptCue]:
    """Parse yt-dlp's JSON3 caption representation into timed cues."""

    try:
        document: Any = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SubtitleParseError(f"Invalid JSON3 subtitle data: {exc.msg}") from exc

    if not isinstance(document, dict):
        raise SubtitleParseError("JSON3 subtitle data must be an object.")
    events = document.get("events")
    if not isinstance(events, list):
        raise SubtitleParseError("JSON3 subtitle data has no events list.")

    raw_cues: list[tuple[int, int | None, str]] = []
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("segs"), list):
            continue
        pieces = [
            str(segment.get("utf8", ""))
            for segment in event["segs"]
            if isinstance(segment, dict) and segment.get("utf8") is not None
        ]
        text = "".join(pieces)
        if not text.strip():
            continue

        start_ms = _integer(event.get("tStartMs", event.get("t", 0)), default=0)
        duration_value = event.get("dDurationMs", event.get("d"))
        duration_ms = _integer(duration_value, default=None)
        raw_cues.append((max(0, start_ms), duration_ms, text))

    cues: list[TranscriptCue] = []
    for index, (start_ms, duration_ms, text) in enumerate(raw_cues):
        if duration_ms is None or duration_ms <= 0:
            next_start = raw_cues[index + 1][0] if index + 1 < len(raw_cues) else start_ms + 1000
            end_ms = max(start_ms + 1, next_start)
        else:
            end_ms = max(start_ms + 1, start_ms + duration_ms)
        cues.append(TranscriptCue(start_ms=start_ms, end_ms=end_ms, text=text))
    return cues


def _integer(value: Any, *, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(float(value))
    except TypeError, ValueError:
        return default

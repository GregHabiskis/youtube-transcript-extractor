from __future__ import annotations

import re

from .models import TranscriptCue

TIMESTAMP_RE = re.compile(
    r"^(?:(?P<hours>\d+):)?(?P<minutes>\d{2}):(?P<seconds>\d{2})[\.,](?P<millis>\d{3})$"
)


def parse_vtt(payload: str) -> list[TranscriptCue]:
    """Parse WebVTT or SRT-like cue blocks without depending on FFmpeg."""

    lines = payload.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").split("\n")
    cues: list[TranscriptCue] = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        upper = line.upper()
        if upper == "WEBVTT" or upper.startswith(("NOTE", "STYLE", "REGION")):
            index = _skip_block(lines, index + 1)
            continue

        timing_line_index = index if "-->" in line else index + 1
        if timing_line_index >= len(lines) or "-->" not in lines[timing_line_index]:
            index = _skip_block(lines, index + 1)
            continue

        timing_line = lines[timing_line_index]
        start_part, end_part = timing_line.split("-->", 1)
        start_ms = parse_timestamp(start_part.strip())
        end_token = end_part.strip().split(maxsplit=1)[0]
        end_ms = parse_timestamp(end_token)
        if start_ms is None or end_ms is None or end_ms <= start_ms:
            index = _skip_block(lines, timing_line_index + 1)
            continue

        text_lines: list[str] = []
        index = timing_line_index + 1
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index])
            index += 1
        text = "\n".join(text_lines).strip()
        if text:
            cues.append(TranscriptCue(start_ms=start_ms, end_ms=end_ms, text=text))

    return cues


def parse_timestamp(value: str) -> int | None:
    match = TIMESTAMP_RE.fullmatch(value.strip())
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis = int(match.group("millis"))
    if minutes > 59 or seconds > 59:
        return None
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def _skip_block(lines: list[str], index: int) -> int:
    while index < len(lines) and lines[index].strip():
        index += 1
    return index + 1

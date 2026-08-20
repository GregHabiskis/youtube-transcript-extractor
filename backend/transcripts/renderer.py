from __future__ import annotations

from collections.abc import Iterable

from .models import TranscriptBlock


def format_timestamp(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds))
    total_seconds, millis = divmod(milliseconds, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def render_plaintext(
    *,
    title: str,
    channel: str,
    url: str,
    upload_date: str | None,
    source: str | None,
    language: str | None,
    blocks: Iterable[TranscriptBlock],
) -> str:
    lines = [f"Title: {title}", f"Channel: {channel}", f"URL: {url}"]
    if upload_date:
        lines.append(f"Upload date: {upload_date}")
    if source:
        lines.append(f"Caption source: {source.title()}")
    if language:
        lines.append(f"Caption language: {language}")
    lines.append("")

    for block in blocks:
        lines.extend(
            [
                f"[{format_timestamp(block.start_ms)} --> {format_timestamp(block.end_ms)}]",
                block.text,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"

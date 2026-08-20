from __future__ import annotations

import re
import unicodedata


def sanitize_filename(title: str, *, max_length: int = 120) -> str:
    """Return a cross-platform filename stem without path traversal characters."""

    value = unicodedata.normalize("NFKC", title)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")[:max_length].rstrip(" .")
    value = value or "transcript"
    if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", value):
        return f"transcript-{value.lower()}"
    return value


def transcript_filename(index: int, title: str) -> str:
    return f"{index:03d}-{sanitize_filename(title)}.txt"

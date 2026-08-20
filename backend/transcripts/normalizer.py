from __future__ import annotations

import html
import re

HTML_TAG_RE = re.compile(r"<[^>]*>")
VTT_POSITIONING_RE = re.compile(r"\{\\[^}]+\}")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_caption_text(text: str) -> str:
    """Remove caption markup while leaving spoken wording untouched."""

    value = html.unescape(text)
    value = HTML_TAG_RE.sub("", value)
    value = VTT_POSITIONING_RE.sub("", value)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return WHITESPACE_RE.sub(" ", value).strip()

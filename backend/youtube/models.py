from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    id: str
    title: str
    url: str
    channel: str
    channel_url: str | None = None
    upload_date: str | None = None
    duration_seconds: float | None = None
    thumbnail: str | None = None
    index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration"] = format_duration(self.duration_seconds)
        return data


@dataclass(frozen=True, slots=True)
class InspectionResult:
    kind: str
    source_url: str
    channel: str
    channel_url: str | None
    videos: list[VideoMetadata]
    requested_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_url": self.source_url,
            "channel": self.channel,
            "channel_url": self.channel_url,
            "requested_count": self.requested_count,
            "found_count": len(self.videos),
            "videos": [video.to_dict() for video in self.videos],
        }


def format_duration(seconds: float | None) -> str | None:
    if seconds is None or seconds < 0:
        return None
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

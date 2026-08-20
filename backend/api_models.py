from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.youtube.service import validate_language


class InspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    latest_videos: int = Field(default=20, ge=1, le=500)


class TranscriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    language: str = Field(default="en", min_length=1, max_length=50)

    @field_validator("language")
    @classmethod
    def validate_language_code(cls, value: str) -> str:
        return validate_language(value)

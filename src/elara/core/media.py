"""Bounded, inline media supplied explicitly by the user; never filesystem paths."""

import base64
import binascii
import io
import wave
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AttachedMedia(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=255)
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "audio/wav"]
    data: str = Field(min_length=1, max_length=5_600_000, repr=False)
    source: Literal["image", "audio", "video_frame", "video_audio"]
    timestamp: float | None = Field(default=None, ge=0, le=30, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_media(self) -> "AttachedMedia":
        if any(c in self.name for c in "/\\\x00\r\n") or self.name.startswith("."):
            raise ValueError("Use a plain filename")
        try:
            raw = base64.b64decode(self.data, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid media encoding") from None
        if not raw or len(raw) > 4 * 1024 * 1024:
            raise ValueError("Media must be at most 4 MiB per part")
        if self.mime_type == "audio/wav":
            if self.source not in {"audio", "video_audio"}:
                raise ValueError("Audio source mismatch")
            try:
                with wave.open(io.BytesIO(raw)) as audio:
                    if (
                        audio.getnchannels() != 1
                        or audio.getsampwidth() != 2
                        or audio.getframerate() != 16000
                        or not 0 < audio.getnframes() <= 480000
                        or len(audio.readframes(audio.getnframes())) != audio.getnframes() * 2
                    ):
                        raise ValueError("Use mono 16 kHz PCM WAV up to 30 seconds")
            except (wave.Error, EOFError):
                raise ValueError("Invalid WAV audio") from None
        else:
            if self.source not in {"image", "video_frame"}:
                raise ValueError("Image source mismatch")
            valid = (
                self.mime_type == "image/png"
                and raw.startswith(b"\x89PNG\r\n\x1a\n")
                or self.mime_type == "image/jpeg"
                and raw.startswith(b"\xff\xd8\xff")
                or self.mime_type == "image/webp"
                and raw.startswith(b"RIFF")
                and raw[8:12] == b"WEBP"
            )
            if not valid:
                raise ValueError("Media bytes do not match the image type")
        if self.source == "video_frame" and self.timestamp is None:
            raise ValueError("Video frames need a timestamp")
        return self


def validate_media_batch(media: tuple[AttachedMedia, ...]) -> None:
    if len(media) > 10 or sum(len(item.data) for item in media) > 16_000_000:
        raise ValueError("Use at most ten media parts and 16 MB of encoded media per message")
    if sum(item.mime_type == "audio/wav" for item in media) > 1:
        raise ValueError("Use one audio clip or video soundtrack per message")

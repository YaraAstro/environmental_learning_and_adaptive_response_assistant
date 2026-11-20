import base64
import io
import wave
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import ValidationError
from pydantic_ai.messages import BinaryContent

from elara.api.web import ChatInput
from elara.core.contracts import AgentRequest
from elara.core.inference import InferenceError
from elara.core.media import AttachedMedia
from elara.core.settings import InferenceSettings
from elara.inference import ollama
from elara.inference.ollama import describe_model, multimodal_prompt, validate_media_support


def png_data():
    return base64.b64encode(bytes.fromhex("89504e470d0a1a0a") + b"test image placeholder").decode()


def wav_data(*, frames=160, channels=1, rate=16000, width=2):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.setframerate(rate)
        audio.writeframes(b"\0" * frames * channels * width)
    return base64.b64encode(buffer.getvalue()).decode()


def image(**changes):
    return AttachedMedia.model_validate(
        {"name": "sample.png", "mime_type": "image/png", "source": "image", "data": png_data()}
        | changes
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"data": "https://example.com/private.png"},
        {"data": "!!!"},
        {"data": base64.b64encode(b"not an image").decode()},
        {"name": "../private.png"},
        {"name": ".hidden.png"},
        {"name": "bad\nname.png"},
        {"source": "audio"},
        {"source": "video_frame"},
        {"source": "video_frame", "timestamp": 31},
        {"source": "video_frame", "timestamp": float("nan")},
        {"data": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * (4 * 1024 * 1024)).decode()},
    ],
)
def test_reject_invalid_image_input(changes):
    with pytest.raises(ValidationError):
        image(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"channels": 2},
        {"rate": 48000},
        {"width": 1},
        {"frames": 480001},
        {"frames": 0},
    ],
)
def test_reject_invalid_audio_format_or_duration(changes):
    with pytest.raises(ValidationError):
        AttachedMedia(name="a.wav", mime_type="audio/wav", source="audio", data=wav_data(**changes))


def test_bounded_media_batches_at_both_entry_points():
    audio = AttachedMedia(name="a.wav", mime_type="audio/wav", source="audio", data=wav_data())
    for media in [(image(),) * 11, (audio, audio)]:
        with pytest.raises(ValidationError):
            AgentRequest(message="test", media=media)
        with pytest.raises(ValidationError):
            ChatInput(session_id=uuid4(), message="test", media=media)
    large = image(data=base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 4_000_000).decode())
    with pytest.raises(ValidationError):
        AgentRequest(message="test", media=(large,) * 4)


@pytest.mark.parametrize("cut", [0, 4, 12, 20, 36, 43, 50])
def test_truncated_wav_is_rejected(cut):
    raw = base64.b64decode(wav_data())[:cut]
    with pytest.raises(ValidationError):
        AttachedMedia(
            name="broken.wav",
            mime_type="audio/wav",
            source="audio",
            data=base64.b64encode(raw).decode(),
        )


def test_wav_cannot_be_disguised_as_image():
    with pytest.raises(ValidationError):
        image(data=wav_data())


def test_multimodal_prompt_keeps_binary_out_of_text_and_includes_frame_time():
    part = image(source="video_frame", timestamp=1.25)
    request = AgentRequest(message="Describe this", media=(part,))
    prompt = multimodal_prompt(request)
    assert isinstance(prompt, list)
    assert isinstance(prompt[-1], BinaryContent)
    assert prompt[-1].data == base64.b64decode(part.data)
    assert part.data not in prompt[0]
    assert "1.25" in prompt[0] and "video_frame" in prompt[0]
    assert part.data not in repr(request)
    assert part.data not in repr(part)


def test_capabilities_fail_closed_including_unknown_metadata():
    request = AgentRequest(message="Look", media=(image(),))
    for info in [
        {},
        {"capabilities": None},
        {"capabilities": ["completion"]},
        {"capabilities": "vision"},
    ]:
        with pytest.raises(InferenceError, match="vision"):
            validate_media_support(request, info)
    validate_media_support(request, {"capabilities": ["vision"]})
    audio = AttachedMedia(name="a.wav", mime_type="audio/wav", source="audio", data=wav_data())
    with pytest.raises(InferenceError, match="audio"):
        validate_media_support(
            AgentRequest(message="Listen", media=(audio,)), {"capabilities": ["vision"]}
        )


def test_model_details_use_metadata_without_exposing_templates(monkeypatch):
    original = httpx.Client
    metadata = {
        "details": {"format": "gguf", "parameter_size": "2B", "quantization_level": "Q4_K_M"},
        "capabilities": ["completion", "vision", "audio"],
        "template": "private template",
        "license": "irrelevant license",
        "model_info": {"model.context_length": 32000, "private.path": "private path"},
    }
    monkeypatch.setattr(
        ollama.httpx,
        "Client",
        lambda **kw: original(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=metadata)), **kw
        ),
    )
    details = describe_model(InferenceSettings(provider="ollama", model="test:local"))
    assert details["inputs"] == {"images": True, "audio": True, "video": True}
    assert details["details"]["parameter_size"] == "2B"
    assert details["model_info"] == {"model.context_length": 32000}
    assert "private" not in str(details)
    assert describe_model(InferenceSettings())["inputs"]["audio"] is False

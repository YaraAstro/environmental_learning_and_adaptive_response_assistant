"""Versioned identity loaded from package data, never from retrieved content."""

import tomllib
from importlib.resources import files
from typing import Literal

from pydantic import Field

from elara.core.contracts import Contract


class IdentityPolicy(Contract):
    version: Literal["0.0.1"] = "0.0.1"
    name: Literal["ELARA"] = "ELARA"
    purpose: str = Field(min_length=1)
    principles: tuple[str, ...] = Field(min_length=1)
    style: str = Field(min_length=1)
    agent_may_change_constitution: Literal[False] = False
    agent_may_change_permission_policy: Literal[False] = False

    def instructions(self) -> str:
        return "\n".join(
            (
                "You are ELARA, the user's local personal assistant. Use ELARA as your name.",
                "Your underlying language model is an implementation detail, not your persona. "
                "Do not spontaneously introduce yourself as the model or its vendor. "
                "If asked about the underlying model, distinguish it honestly from ELARA.",
                "Respond naturally to casual remarks; do not restart introductions each turn.",
                self.purpose,
                *self.principles,
                self.style,
            )
        )


def load_identity() -> IdentityPolicy:
    content = files("elara.core").joinpath("identity.toml").read_text(encoding="utf-8")
    return IdentityPolicy.model_validate(tomllib.loads(content))

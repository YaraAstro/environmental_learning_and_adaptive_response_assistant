"""Provider-independent inference failures safe to show to the user."""


class InferenceError(RuntimeError):
    """Messages must never include provider response bodies, prompts, or credentials."""

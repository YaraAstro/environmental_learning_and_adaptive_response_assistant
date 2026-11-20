# ADR 0003: First live provider is local Ollama

Status: adapter implemented; real generation still requires the user's local smoke test.

The user selected Ollama for the first real conversations. Keep mock mode as the
zero-network default and provide `config/elara.ollama.example.toml` for explicit
local inference. The starter model tag is `qwen3:4b`; it can be changed to another
installed local chat model. ELARA does not install or download models itself.

## Behavior

Use the installed Pydantic AI `OllamaModel`/`OllamaProvider` with an explicit
OpenAI-compatible client pointing to the loopback daemon. The OpenAI SDK is a
protocol client here, not an OpenAI cloud connection. Pass a fixed placeholder
key rather than reading keys or endpoint overrides from the environment.
The locked OpenAI SDK uses HTTPX2, so ELARA uses the matching transport explicitly;
the SDK/client construction boundary is covered by a synchronous unit test.

Only literal loopback addresses (`127.0.0.1` or `[::1]`) with an explicit port and
`/v1` path are accepted. Disable environment proxies and HTTP redirects. Reject
cloud model names, and inspect `/api/show` before every generation to reject
remote model aliases and malformed metadata. This assumes the local daemon is
trusted; ELARA cannot protect against an administrator replacing it with a relay.
For additional daemon-level protection, Ollama can be configured separately to
disable cloud features; ELARA does not modify the user's daemon configuration.

No provider fallback, SDK retry, model retry, tools, or hosted tracing is enabled.
One request may produce at most one model call. Apply an overall response timeout,
a short metadata/connect timeout, a character-based input guard, and an output
token setting. Character limits are not exact model token/context-window limits;
output limits depend on the backend. These are not OS RAM/VRAM caps.
Request non-thinking output for concise starter conversations; models that cannot
disable thinking may retain their own behavior.

Each response creates and closes its own HTTP client so interactive CLI calls
cannot reuse connections attached to an earlier event loop. User/assistant history
is mapped from domain contracts, and existing saved-session behavior is preserved.
Successful real responses have `simulated=False`; failed inference never produces
a fake replacement response or saves a partial conversation exchange.

`doctor` stays offline. `provider check` sends model metadata only, whereas
`provider smoke` generates a fixed synthetic greeting without saving a session.
Backend error bodies and credentials are never printed by CLI failure handling.

## Validation and references

Tests cover endpoint/model policy, metadata checks, request budgets, history
translation, and command behavior. Async tests use HTTPX MockTransport to exercise
the real SDK/adapter without live inference. They remain enabled in CI; this
restricted Windows session cannot create the sockets required by asyncio.

- https://pydantic.dev/docs/ai/models/ollama/
- https://docs.ollama.com/api/openai-compatibility
- https://docs.ollama.com/api-reference/show-model-details
- https://ollama.com/library/qwen3:4b

# ELARA

**Environmental Learning and Adaptive Response Assistant**

A Windows-first, Linux-ready, local-first companion. ELARA owns its identity,
permissions, and future memory/learning policies; model providers are adapters.

## Current status

This repository includes the foundation, **local conversation persistence**, and
an **Ollama adapter for real local conversations**. The default profile still uses
Pydantic AI's offline `TestModel`; real inference requires the explicit Ollama
profile below. Filesystem tools, environment collection, and autonomous learning
are not enabled. This is not yet the full v0.1 companion.

Included:

- Python 3.12 package and `elara` CLI entry point.
- Validated TOML settings and a packaged, versioned identity constitution.
- Typed agent contracts and a Pydantic AI mock adapter.
- Local Ollama adapter with history replay, timeout/input/output limits, and provider checks.
- Deny-by-default policy and a synthetic gateway scoped to actor/session/resource.
- Security, configuration, runtime, and CLI tests; Windows/Linux CI configuration.
- SQLite FTS5 preflight, synthetic sandbox, and starter evaluation scenarios.
- SQLite migrations, atomic saved conversations, history replay, export/deletion,
  consistent backups, and append-only action audit records.

## Windows setup

From this directory, run in PowerShell:

```powershell
.\scripts\bootstrap.ps1
```

This requires network access to PyPI and uv's Python download host. It installs
workspace-local uv when needed, downloads Python 3.12, creates `.venv`, resolves
dependencies into `uv.lock`, and runs lint, type checks, tests, and `doctor`.
The local wrapper keeps downloads/caches in ignored workspace directories.
It does not change global PATH or replace system Python. Python with pip is
needed only to bootstrap uv when uv is not already installed.

Then:

```powershell
.\scripts\uv.ps1 run elara doctor
.\scripts\uv.ps1 run elara chat "Hello ELARA"
.\scripts\uv.ps1 run elara chat
.\scripts\uv.ps1 run elara settings show
.\scripts\uv.ps1 run elara --config config/elara.example.toml settings show
```

The default `chat` uses a fixed simulated response. No keys, model downloads, or
Ollama service are needed in mock mode. Plain chat is temporary; saving is opt-in.

## Real conversations with Ollama

Open the installed Ollama application. If it is not running as an app, start
`ollama serve` in a separate terminal. Then install the configured starter model
and check the connection:

```powershell
ollama pull qwen3:4b
.\scripts\uv.ps1 run elara --config config/elara.ollama.example.toml provider check
.\scripts\uv.ps1 run elara --config config/elara.ollama.example.toml provider smoke
.\scripts\uv.ps1 run elara --config config/elara.ollama.example.toml chat --save
```

`provider check` verifies model metadata without sending a prompt; `provider smoke`
generates one fixed greeting without saving a session. Real replies print `ELARA:`;
mock replies print `ELARA [simulation]:`. An error never silently switches modes.

The example uses [qwen3:4b](https://ollama.com/library/qwen3:4b). You can use another
installed local chat model by copying the profile to `config/elara.toml`, changing
`inference.model` to its exact tag from `ollama list`, and passing that config path.
Both example profiles point at the same `.data` directory, so existing session IDs
can be resumed with `chat --session SESSION_ID` under the Ollama profile.

No API key is needed. This adapter accepts only literal loopback endpoints and
rejects cloud tags, remote aliases, redirects, and environment proxy overrides.
It does not start services, download models, or modify Ollama's configuration.
The local daemon must be trusted. The OpenAI-compatible SDK connects to Ollama,
not OpenAI's hosted service. See [ADR 0003](docs/decisions/0003-local-ollama.md).

If a first model load times out, increase `request_timeout_seconds` or choose a
smaller installed model. `max_context_characters` bounds input text rather than
exact model tokens; it does not change Ollama's context window or RAM allocation.

## Save and resume a conversation

Use the example configuration to keep development data in the ignored `.data`
folder. Without an explicit config, runtime data uses the per-user platformdirs
location. All commands must use the same configuration to see the same sessions.

```powershell
.\scripts\uv.ps1 run elara --config config/elara.example.toml chat --save "Hello ELARA"
.\scripts\uv.ps1 run elara --config config/elara.example.toml sessions list
# Replace SESSION_ID with the UUID printed by chat or sessions list.
.\scripts\uv.ps1 run elara --config config/elara.example.toml chat --session SESSION_ID "Continue"
.\scripts\uv.ps1 run elara --config config/elara.example.toml sessions show SESSION_ID
.\scripts\uv.ps1 run elara --config config/elara.example.toml sessions export SESSION_ID --output session.json
.\scripts\uv.ps1 run elara --config config/elara.example.toml database backup backup.sqlite3
.\scripts\uv.ps1 run elara --config config/elara.example.toml sessions delete SESSION_ID
```

Saved turns are replayed into the runtime after restarting. Each successful
exchange is atomic; failed generation saves no partial exchange, and stale writes
are rejected. Saving history does not yet provide semantic memory or learning.
`sessions audit SESSION_ID` displays action metadata (chat currently has no tools).
`database init` explicitly initializes the schema without starting a chat.

Exports and backups refuse to overwrite existing files. Session deletion removes
the transcript but retains action audit metadata; exports and backups are separate.
Common credential patterns are redacted before storage, but redaction is not a
guarantee for arbitrary secrets or personal data. Database files are unencrypted.
See [persistence decisions](docs/decisions/0002-local-sessions.md) for retention and
[migration recovery](migrations/README.md) for backup-based rollback.

If `uv` is installed globally, the equivalent `uv sync` / `uv run ...` commands
work directly. On Linux, install uv, run `uv python install 3.12`, then
`uv sync --locked` and the same `uv run` commands.

## Dependency verification status

Python 3.12.16, the dependencies, and `uv.lock` are now available. An offline
`uv sync --locked --all-extras` succeeds. CI now always requires the lockfile.

Local synchronous tests cover database operations, rollback, audit enforcement,
redaction, provider configuration, and metadata checks: **83 tests passed**.
Ruff, mypy, `elara doctor`, and
wheel/source-distribution builds passed. The wheel includes its identity and SQL
migration; private data and local caches are excluded from the source archive.

The restricted execution session blocks the loopback
socket pair that Windows asyncio needs to create an event loop. Async/runtime and
chat tests therefore still require an unrestricted Windows host or Windows/Linux
CI. Those tests remain enabled; this limitation is not hidden by skips in CI.
The user's saved mock-chat command was confirmed working in their own PowerShell.
The Ollama API is unreachable from this session, so a real local response has not
been verified here. Run the `provider smoke` command above after installing the model.

To reproduce the subset that does not require an event loop:

```powershell
.\scripts\uv.ps1 run pytest -q -m "not asyncio" --ignore=tests/integration/test_cli.py
.\scripts\uv.ps1 run pytest -q tests/integration/test_cli.py -k "settings_are_safe or doctor_checks or unknown_session"
```

The dependency-free check is available now:

```powershell
python scripts/check_scaffold.py
```

It checks Python syntax, TOML/JSON integrity, and host SQLite FTS5 behavior only.

## Configuration and boundaries

Use `--config PATH` or `ELARA_CONFIG_PATH`; otherwise built-in safe defaults apply.
Relative paths resolve against the config file. Settings do not create folders.
Only documented fields are accepted. Mock and local Ollama are supported; cloud
providers, write tools, observation, and learning remain disabled.
The broad dossier configuration remains a proposal for later milestones.

Identity is packaged in `src/elara/core/identity.toml` so installed builds work
outside this repository. Policy enforcement lives in Python, not in identity text.
Agent output cannot create grants. The gateway requires an audit sink; SQLiteStore
provides durable decision/start/outcome records. The current synthetic gateway is not a
production filesystem sandbox or an authenticated multi-user security boundary.

Runtime data uses `platformdirs`; `.env`, private config, SQLite databases,
caches, and local data are ignored by Git. No provider credentials are loaded.

## Development

```powershell
.\scripts\uv.ps1 run ruff check .
.\scripts\uv.ps1 run ruff format .
.\scripts\uv.ps1 run mypy
.\scripts\uv.ps1 run pytest -q
.\scripts\uv.ps1 build
```

Tests disable live Pydantic AI requests; adapter contract tests use an in-memory
HTTP transport rather than a live endpoint. Core contracts must not import
provider SDKs or OS adapters. See [architecture](docs/architecture.md),
[initial decisions](docs/decisions/0001-foundation.md), and
[next steps](docs/next-steps.md).

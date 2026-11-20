# ELARA

**Environmental Learning and Adaptive Response Assistant**

A Windows-first, Linux-ready, local-first companion. ELARA owns its identity,
permissions, and future memory/learning policies; model providers are adapters.

## Current status

This repository implements **Increment A: the initial foundation scaffold**.
It is not yet the v0.1 companion. The CLI uses Pydantic AI's offline `TestModel`
and labels every response as simulated. It has no live inference, filesystem
tools, environment collection, persistent conversations, or autonomous learning.

Included:

- Python 3.12 package and `elara` CLI entry point.
- Validated TOML settings and a packaged, versioned identity constitution.
- Typed agent contracts and a Pydantic AI mock adapter.
- Deny-by-default policy and a synthetic gateway scoped to actor/session/resource.
- Security, configuration, runtime, and CLI tests; Windows/Linux CI configuration.
- SQLite FTS5 preflight, synthetic sandbox, and starter evaluation scenarios.

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

`chat` is an offline wiring demonstration with a fixed response, not a capable
model or persistent conversation. No keys, model downloads, or Ollama service
are needed for this demonstration.

If `uv` is installed globally, the equivalent `uv sync` / `uv run ...` commands
work directly. On Linux, install uv, run `uv python install 3.12`, then `uv sync`
and the same `uv run` commands. Use `uv sync --locked` after the lockfile exists.

## Dependency verification status

The initial setup session could not resolve PyPI, and only Python 3.13 was
available on the host. Therefore dependencies and Python 3.12 were **not installed**,
`uv.lock` is **not yet generated**, and pytest/Ruff/mypy have **not been run**.
Run the bootstrap command to complete those steps, review and commit the generated
lockfile, then use locked installs. CI temporarily resolves dependencies if a
lockfile is absent; once present, CI requires it to remain consistent.

The dependency-free check is available now:

```powershell
python scripts/check_scaffold.py
```

It checks Python syntax, TOML/JSON integrity, and host SQLite FTS5 behavior only.

## Configuration and boundaries

Use `--config PATH` or `ELARA_CONFIG_PATH`; otherwise built-in safe defaults apply.
Relative paths resolve against the config file. Settings do not create folders.
Only the documented v0.0 fields are accepted; attempts to enable live providers,
write tools, observation, or learning are rejected until those features exist.
The broad dossier configuration remains a proposal for later milestones.

Identity is packaged in `src/elara/core/identity.toml` so installed builds work
outside this repository. Policy enforcement lives in Python, not in identity text.
Agent output cannot create grants. The gateway's decisions are ephemeral test
diagnostics, not durable audit records. The current synthetic gateway is not a
production filesystem sandbox or an authenticated multi-user security boundary.

Runtime data will use `platformdirs`; `.env`, private config, SQLite databases,
caches, and local data are ignored by Git. No credentials are loaded in v0.0.

## Development

```powershell
.\scripts\uv.ps1 run ruff check .
.\scripts\uv.ps1 run ruff format .
.\scripts\uv.ps1 run mypy
.\scripts\uv.ps1 run pytest -q
.\scripts\uv.ps1 build
```

Tests disable live Pydantic AI model requests. Core contracts must not import
provider SDKs or OS adapters. See [architecture](docs/architecture.md),
[initial decisions](docs/decisions/0001-foundation.md), and
[next steps](docs/next-steps.md).

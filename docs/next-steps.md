# Next implementation increment

The local Python 3.12 environment and lockfile are now present. SQLite migrations,
saved sessions, history replay, export/deletion, backup, and action auditing are
implemented. Local Ollama inference is now wired with an explicit profile and
provider diagnostics. Check the README for current validation limits.

1. Run the full async suite on an unrestricted Windows host and in Windows/Linux CI.
2. Start Ollama, install the selected local model, and run `provider smoke` using
   `config/elara.ollama.example.toml` to verify a real provider response.
3. Explicit read-only workspace commands now use the audited gateway. Before
   exposing them to models, strengthen handle-based containment for concurrent
   filesystem changes and verify actual Windows junction behavior on the host.
4. Chat now receives explicitly selected files through audited reads (`--workspace`
   and `--attach`). Verify the live attachment flow with the installed model and run
   the async persistence test. Native model-selected tool calls remain a later step
   after stronger filesystem containment. Test restart, privacy, and permission
   flows before declaring v0.1 complete.

Memory lifecycle, environment sensing, verified learning, skills, and desktop UI
remain later milestones, as ordered in the dossier.

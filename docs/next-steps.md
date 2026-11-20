# Next implementation increment

The local Python 3.12 environment and lockfile are now present. SQLite migrations,
saved sessions, history replay, export/deletion, backup, and action auditing are
implemented. Local Ollama inference is now wired with an explicit profile and
provider diagnostics. User-confirmed live attachment chat works with `lfm3-omni:2b`.
Explicit cross-session memory now supports set/list/forget and local recall on each
turn. The user confirmed CLI memory recall and deletion. Use `scripts/ui.ps1` for
the new local browser interface or `scripts/chat.ps1 --save` for CLI chat. Check the README for
current validation limits.

1. Run the full async suite on an unrestricted Windows host and in Windows/Linux CI.
2. Smoke-test the browser UI: open the printed launch URL, resume a CLI session,
   send a message, edit/forget a memory, attach text, and verify a failed provider
   call leaves no partial saved turn. Verify memory across a fresh process too.
3. Explicit read-only workspace commands now use the audited gateway. Before
   exposing them to models, strengthen handle-based containment for concurrent
   filesystem changes and verify actual Windows junction behavior on the host.
4. Chat now receives explicitly selected files through audited reads (`--workspace`
   and `--attach`). Verify the live attachment flow with the installed model and run
   the async persistence test. Native model-selected tool calls remain a later step
   after stronger filesystem containment. Test restart, privacy, and permission
   flows before declaring v0.1 complete.

Richer memory retrieval/lifecycle, environment sensing, verified learning, skills, and native desktop packaging
remain later milestones, as ordered in the dossier.

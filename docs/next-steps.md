# Next implementation increment

The local Python 3.12 environment and lockfile are now present. SQLite migrations,
saved sessions, history replay, export/deletion, backup, and action auditing are
implemented. Local Ollama inference is now wired with an explicit profile and
provider diagnostics. User-confirmed live attachment chat works with `lfm3-omni:2b`.
Explicit cross-session memory now supports set/list/forget and local recall on each
turn. The user confirmed CLI memory recall and deletion. Use `scripts/ui.ps1` for
the new local browser interface or `scripts/chat.ps1 --save` for CLI chat. Check the README for
current validation limits. The next UI increment is implemented in React/TypeScript
with Vite: model metadata, image/audio inputs, and sampled video with optional sound.
Browser conversions are local and media is sent for one turn without storing its bytes.

1. Run `.\scripts\verify.ps1 -CheckOllama` from a normal PowerShell session for the
   full suite, lint, types, packaging, and a metadata-only Ollama check. Add
   `-RebuildUI` to install locked frontend dependencies and rebuild it too.
   Any failed automated check yields a nonzero exit code. This command does not
   claim to verify browser codecs or live media replies. Windows/Linux CI also
   runs the full async suite.
2. Smoke-test the browser UI: open the printed launch URL, resume a CLI session,
   send a message, edit/forget a memory, attach text, and verify a failed provider
   call leaves no partial saved turn. Verify memory across a fresh process too.
   Check Model details against installed Ollama, then test one image, a short audio
   clip, and video both with and without its soundtrack. Inspect the preview labels.
   Unsupported model capabilities must stop the turn before generation. Test a
   failed decode and verify that the draft/previous attachments remain intact.
   This environment cannot validate live Ollama or browser media codecs.
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

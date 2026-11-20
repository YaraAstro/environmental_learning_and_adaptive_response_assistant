# Next implementation increment

The local Python 3.12 environment and lockfile are now present. SQLite migrations,
saved sessions, history replay, export/deletion, backup, and action auditing are
implemented. Check the README for current validation limits.

1. Run the full async suite on an unrestricted Windows host and in Windows/Linux CI.
2. Add one explicitly selected live provider behind `AgentRuntime`, with request
   limits and enforced local/cloud privacy policy. Verify a real provider call.
3. Add a read-only sandbox adapter through the gateway; test traversal, symlinks,
   Windows junctions, scoped consent, and denied actions with zero OS calls.
4. Connect the runtime to audited tools and test the full conversation, session
   restart, privacy, and permission flows before declaring v0.1 complete.

Memory lifecycle, environment sensing, verified learning, skills, and desktop UI
remain later milestones, as ordered in the dossier.

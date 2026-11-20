# Next implementation increment

1. Complete bootstrap with network access; review the resolved dependencies and
   commit `uv.lock` only after Ruff, mypy, pytest, doctor, and build pass.
2. Implement SQLite migrations, sessions/turns, audit events, and restart tests.
3. Add one explicitly selected live provider behind `AgentRuntime`, with request
   limits and enforced local/cloud privacy policy. Verify a real provider call.
4. Add a read-only sandbox adapter through the gateway; test traversal, symlinks,
   Windows junctions, scoped consent, and denied actions with zero OS calls.
5. Replace simulated CLI conversations with persistent conversations and useful
   failure messages. Record v0.1 completion only when its exit gates pass.

Memory lifecycle, environment sensing, verified learning, skills, and desktop UI
remain later milestones, as ordered in the dossier.

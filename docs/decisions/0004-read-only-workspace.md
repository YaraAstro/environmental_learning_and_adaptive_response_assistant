# 0004: Explicit read-only workspace commands

The CLI accepts a mandatory folder root and a relative path for one read or list
operation. Trusted application wiring creates an exact actor/session/capability/
resource grant for that invocation. The gateway records the decision before
dispatch, then start and success/failure events. Failure to record a decision or
start prevents execution. Audit failure after reading prevents returning the
result. Root validation happens before grant creation and is not audited.

No grants originate from model output. Standalone workspace commands do not invoke
a model. Chat can now accept explicitly selected attachments through a wrapper
that grants those exact reads per turn, associates audits with the chat session,
and supplies their contents as reference text. It has no registered model-selected
workspace tools. Autonomous-action settings
remain disabled. A command's audit UUID is separate from conversation sessions;
`sessions audit UUID` retrieves its records using the same configuration.

The adapter rejects absolute/drive/UNC paths, parent traversal, hidden components,
alternate streams, and Windows trailing-dot/space ambiguity. It checks every
component for symbolic links and reparse points, and rejects hardlinked file
reads. UTF-8 text reads are limited to 64 KiB and five extensions; listings are
nonrecursive with a 200-entry cap, counting hidden entries too. A listing fails
if it encounters a visible link rather than silently following it.

This adapter assumes a trusted directory without adversarial concurrent changes.
Path checks and file identity checks reduce mistakes but do not eliminate races
between checks and filesystem operations. Handle-based containment and real
Windows junction coverage are prerequisites for stronger sandbox claims. The
root itself may be any explicitly chosen local folder; extension filtering is
not secret detection. Contents print to the caller's terminal, never to the audit
log. Chat attachments do send the selected contents to local Ollama, and answers
may quote them. Audit records contain a digest of the requested relative path;
they do not identify the root or preserve read contents for replay.

Unit tests cover traversal, Windows path syntax, simulated reparse attributes,
hardlink counts, size/encoding limits, and denial before adapter calls. Real link
tests skip when the host cannot create links. CLI tests verify durable audit
events for both successful and rejected reads. Writes, shell commands, automatic
folder selection, and model tool registration remain outside this increment.

# Foundation architecture

The source of the plan is the existing ELARA Project Dossier in the adjacent
`../assets/ELARA_Project_Dossier` directory, especially the implementation guide,
project map, and environment setup. Those documents describe future capabilities;
this repository's README describes what actually exists.

| Package | Responsibility now |
| --- | --- |
| `core` | Immutable contracts, validated settings, versioned identity |
| `actions` | Pure policy evaluator; synthetic gateway and scoped grants |
| `inference` | Offline Pydantic AI adapter implementing `AgentRuntime` |
| `app.py` | Dependency composition |
| `cli.py` | `doctor`, `settings show`, and simulated `chat` |

Reserved package boundaries: `memory`, `context`, `cognition`, `verification`,
`platform`, `knowledge`, `api`, and `observability`. They contain no implementation
until a milestone needs them. Core code depends only on Python/Pydantic and path
configuration utilities. Framework adapters depend on core contracts.

The initial gateway only dispatches `demo.echo` against `synthetic`. A trusted
caller supplies grants bound to actor and session UUIDs. Every other action and
resource is denied. No model-facing grant creation, arbitrary callable dispatch,
OS reads, shell tools, or network tools are exposed.

This proves denial-before-dispatch, not complete security. Before real tools:
implement authenticated scopes, immutable arguments, expiring authorizations,
durable audits, path/link checks, race-resistant execution, and adapter-level
enforcement. Persistent data needs migrations and lifecycle controls first.

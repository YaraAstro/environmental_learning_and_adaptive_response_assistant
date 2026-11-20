"""The only registered adapter is synthetic and has no OS/network capabilities."""

import hashlib
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from elara.actions.policy import ActionRequest, AuthorizationPolicy, Decision
from elara.core.audit import AuditEvent, AuditSink


class SyntheticAdapter(Protocol):
    def echo(self) -> str: ...


class ActionDenied(PermissionError):
    pass


class ActionGateway:
    def __init__(
        self, policy: AuthorizationPolicy, adapter: SyntheticAdapter, *, audit: AuditSink
    ) -> None:
        self._policy = policy
        self._adapter = adapter
        self._audit = audit
        self._decisions: list[Decision] = []

    @property
    def decisions(self) -> tuple[Decision, ...]:
        """Convenience view; the supplied audit sink owns the actual event records."""
        return tuple(self._decisions)

    def execute(self, request: ActionRequest) -> str:
        decision = self._policy.evaluate(request)
        self._decisions.append(decision)
        event = AuditEvent.model_validate(
            {
                "action_id": uuid4(),
                "actor_id": request.actor_id,
                "session_id": request.session_id,
                "kind": "action.decision",
                "capability": "demo.echo" if request.capability == "demo.echo" else "unsupported",
                "resource_digest": hashlib.sha256(request.resource.encode()).hexdigest(),
                "outcome": decision.outcome,
                "reason": decision.reason,
            }
        )
        self._audit.record(event)
        if decision.outcome != "allow":
            raise ActionDenied(decision.reason)

        def record(kind: str) -> None:
            self._audit.record(
                AuditEvent.model_validate(
                    {
                        **event.model_dump(),
                        "id": uuid4(),
                        "kind": kind,
                        "occurred_at": datetime.now(UTC),
                    }
                )
            )

        record("action.started")
        try:
            result = self._adapter.echo()
        except Exception:
            record("action.failed")
            raise
        record("action.succeeded")
        return result

"""Pure authorization. Grants come from trusted application wiring, not the model."""

from typing import Literal
from uuid import UUID

from elara.core.contracts import Contract


class ActionRequest(Contract):
    actor_id: UUID
    session_id: UUID
    capability: str
    resource: str


class Grant(Contract):
    actor_id: UUID
    session_id: UUID
    capability: Literal["demo.echo", "workspace.read", "workspace.list"]
    resource: str = "synthetic"


class Decision(Contract):
    outcome: Literal["allow", "deny"]
    reason: str


class AuthorizationPolicy:
    def __init__(self, grants: tuple[Grant, ...] = ()) -> None:
        self._grants = grants

    def evaluate(self, request: ActionRequest) -> Decision:
        if request.capability not in {"demo.echo", "workspace.read", "workspace.list"} or (
            request.capability == "demo.echo" and request.resource != "synthetic"
        ):
            return Decision(outcome="deny", reason="unsupported_capability_or_resource")
        for grant in self._grants:
            if (
                grant.actor_id == request.actor_id
                and grant.session_id == request.session_id
                and grant.capability == request.capability
                and grant.resource == request.resource
            ):
                return Decision(outcome="allow", reason="explicit_scoped_grant")
        return Decision(outcome="deny", reason="no_matching_grant")

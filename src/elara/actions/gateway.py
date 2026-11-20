"""The only registered adapter is synthetic and has no OS/network capabilities."""

from typing import Protocol

from elara.actions.policy import ActionRequest, AuthorizationPolicy, Decision


class SyntheticAdapter(Protocol):
    def echo(self) -> str: ...


class ActionDenied(PermissionError):
    pass


class ActionGateway:
    def __init__(self, policy: AuthorizationPolicy, adapter: SyntheticAdapter) -> None:
        self._policy = policy
        self._adapter = adapter
        self._decisions: list[Decision] = []

    @property
    def decisions(self) -> tuple[Decision, ...]:
        """Ephemeral test diagnostics, not a durable audit trail."""
        return tuple(self._decisions)

    def execute(self, request: ActionRequest) -> str:
        decision = self._policy.evaluate(request)
        self._decisions.append(decision)
        if decision.outcome != "allow":
            raise ActionDenied(decision.reason)
        return self._adapter.echo()

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from elara.actions.gateway import ActionDenied, ActionGateway
from elara.actions.policy import ActionRequest, AuthorizationPolicy, Grant
from elara.core.audit import AuditEvent
from elara.memory.database import connect
from elara.memory.store import SQLiteStore


class Adapter:
    calls = 0

    def echo(self) -> str:
        self.calls += 1
        return "synthetic"


def test_denial_is_durable_and_resource_text_is_not_logged(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    adapter = Adapter()
    request = ActionRequest(
        actor_id=uuid4(),
        session_id=uuid4(),
        capability="shell.execute",
        resource="private/path/with-a-secret",
    )
    gateway = ActionGateway(AuthorizationPolicy(), adapter, audit=store)
    with pytest.raises(ActionDenied):
        gateway.execute(request)
    events = SQLiteStore(store.path).audit_events(request.session_id)
    assert [event.kind for event in events] == ["action.decision"]
    assert events[0].outcome == "deny"
    assert request.resource not in events[0].model_dump_json()
    assert adapter.calls == 0


def test_success_is_audited_and_audit_survives_session_deletion(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    session = store.create_session()
    grant = Grant(actor_id=uuid4(), session_id=session.id, capability="demo.echo")
    gateway = ActionGateway(AuthorizationPolicy((grant,)), Adapter(), audit=store)
    gateway.execute(ActionRequest(**grant.model_dump()))
    store.delete_session(session.id)
    events = store.audit_events(session.id)
    assert [event.kind for event in events] == [
        "action.decision",
        "action.started",
        "action.succeeded",
    ]
    assert len({event.action_id for event in events}) == 1
    assert len({event.id for event in events}) == 3
    with connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM audit_events")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE audit_events SET event_json = '{}'")


@pytest.mark.parametrize("fail_on", [1, 2])
def test_audit_failure_blocks_execution(fail_on: int) -> None:
    class FailingAudit:
        calls = 0

        def record(self, event: AuditEvent) -> None:
            self.calls += 1
            if self.calls == fail_on:
                raise OSError("disk full")

    grant = Grant(actor_id=uuid4(), session_id=uuid4(), capability="demo.echo")
    adapter = Adapter()
    gateway = ActionGateway(AuthorizationPolicy((grant,)), adapter, audit=FailingAudit())
    with pytest.raises(OSError):
        gateway.execute(ActionRequest(**grant.model_dump()))
    assert adapter.calls == 0


def test_failed_adapter_records_failure_without_exception_contents(tmp_path: Path) -> None:
    class FailingAdapter:
        def echo(self) -> str:
            raise RuntimeError("do not log this secret")

    store = SQLiteStore(tmp_path / "elara.sqlite3")
    grant = Grant(actor_id=uuid4(), session_id=uuid4(), capability="demo.echo")
    gateway = ActionGateway(AuthorizationPolicy((grant,)), FailingAdapter(), audit=store)
    with pytest.raises(RuntimeError):
        gateway.execute(ActionRequest(**grant.model_dump()))
    events = store.audit_events(grant.session_id)
    assert events[-1].kind == "action.failed"
    assert all("secret" not in event.model_dump_json() for event in events)

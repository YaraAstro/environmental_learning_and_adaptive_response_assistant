"""Explicit user-authorized workspace operations, independent of model behavior."""

import argparse
from uuid import uuid4

from elara.actions.gateway import ActionGateway
from elara.actions.policy import ActionRequest, AuthorizationPolicy, Grant
from elara.actions.workspace import WorkspaceReader
from elara.core.settings import Settings
from elara.memory.store import SQLiteStore


class NoSyntheticAction:
    def echo(self) -> str:
        raise PermissionError("Synthetic action unavailable")


def run_workspace(args: argparse.Namespace, settings: Settings) -> int:
    workspace = WorkspaceReader(args.root)
    store = SQLiteStore(settings.data_dir / "database" / "elara.sqlite3")
    grant = Grant(
        actor_id=uuid4(),
        session_id=uuid4(),
        capability="workspace.read" if args.workspace_command == "read" else "workspace.list",
        resource=args.path,
    )
    gateway = ActionGateway(
        AuthorizationPolicy((grant,)), NoSyntheticAction(), audit=store, workspace=workspace
    )
    print(f"Action audit ID: {grant.session_id}")
    print(gateway.execute(ActionRequest(**grant.model_dump())))
    return 0

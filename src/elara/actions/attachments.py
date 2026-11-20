"""Read only caller-selected files; a model cannot expand the selection."""

from pathlib import Path
from uuid import uuid4

from elara.actions.gateway import ActionGateway
from elara.actions.policy import ActionRequest, AuthorizationPolicy, Grant
from elara.actions.workspace import WorkspaceReader
from elara.core.audit import AuditSink
from elara.core.contracts import AgentRequest, AgentResponse, AgentRuntime, AttachedDocument
from elara.core.inference import InferenceError


class NoSyntheticAction:
    def echo(self) -> str:
        raise PermissionError("Synthetic action unavailable")


class AttachmentRuntime:
    def __init__(
        self, runtime: AgentRuntime, root: Path, paths: tuple[str, ...], audit: AuditSink
    ) -> None:
        if not 1 <= len(paths) <= 8 or any(len(path) > 1024 for path in paths):
            raise InferenceError("Select between one and eight files with short relative paths.")
        self._reader = WorkspaceReader(root)
        self._paths = tuple(dict.fromkeys(paths))
        self._runtime = runtime
        self._audit = audit
        self._actor = uuid4()

    def prepare(self, request: AgentRequest) -> AgentRequest:
        grants = tuple(
            Grant(
                actor_id=self._actor,
                session_id=request.session_id,
                capability="workspace.read",
                resource=path,
            )
            for path in self._paths
        )
        gateway = ActionGateway(
            AuthorizationPolicy(grants),
            NoSyntheticAction(),
            audit=self._audit,
            workspace=self._reader,
        )
        documents = []
        total = 0
        for grant in grants:
            content = gateway.execute(ActionRequest(**grant.model_dump()))
            total += len(content)
            if total > 16000:
                raise InferenceError("Attachments exceed 16,000 characters; select smaller files.")
            documents.append(AttachedDocument(path=grant.resource, content=content))
        return request.model_copy(update={"attachments": tuple(documents)})

    async def respond(self, request: AgentRequest) -> AgentResponse:
        return await self._runtime.respond(self.prepare(request))

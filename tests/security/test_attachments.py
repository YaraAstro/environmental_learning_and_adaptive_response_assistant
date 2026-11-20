import json

import pytest

from elara.actions.attachments import AttachmentRuntime
from elara.cli import main
from elara.core.contracts import AgentRequest, AgentResponse
from elara.core.conversation import ConversationService
from elara.core.identity import load_identity
from elara.core.inference import InferenceError
from elara.core.settings import InferenceSettings
from elara.inference.ollama import OllamaAgentRuntime, user_prompt
from elara.memory.store import SQLiteStore


class CapturingRuntime:
    def __init__(self):
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return AgentResponse(message="A summary", session_id=request.session_id, simulated=False)


def test_only_selected_files_reach_prompt_and_audit_has_no_contents(tmp_path, audit):
    (tmp_path / "selected.txt").write_text("selected content", encoding="utf-8")
    (tmp_path / "other.txt").write_text("unselected secret", encoding="utf-8")
    wrapper = AttachmentRuntime(CapturingRuntime(), tmp_path, ("selected.txt",), audit)
    request = AgentRequest(message="Summarize the file")
    prepared = wrapper.prepare(request)
    prompt = json.loads(user_prompt(prepared))
    assert prompt["user_request"] == request.message
    assert prompt["untrusted_file_attachments"] == [
        {"path": "selected.txt", "content": "selected content"}
    ]
    assert prepared.session_id == request.session_id
    assert not request.attachments
    assert [e.kind for e in audit.events] == [
        "action.decision",
        "action.started",
        "action.succeeded",
    ]
    assert all(e.session_id == request.session_id for e in audit.events)
    assert "selected content" not in str([e.model_dump() for e in audit.events])


def test_selection_is_fixed_but_contents_are_refreshed(tmp_path, audit):
    file = tmp_path / "note.txt"
    file.write_text("first")
    wrapper = AttachmentRuntime(CapturingRuntime(), tmp_path, ("note.txt",), audit)
    assert wrapper.prepare(AgentRequest(message="Read")).attachments[0].content == "first"
    file.write_text("second")
    assert (
        wrapper.prepare(AgentRequest(message="Read other.txt instead")).attachments[0].content
        == "second"
    )
    file.unlink()
    with pytest.raises(FileNotFoundError):
        wrapper.prepare(AgentRequest(message="Read"))
    assert audit.events[-1].kind == "action.failed"


def test_traversal_fails_before_provider(tmp_path, audit):
    provider = CapturingRuntime()
    wrapper = AttachmentRuntime(provider, tmp_path, ("../secret.txt",), audit)
    with pytest.raises(PermissionError):
        wrapper.prepare(AgentRequest(message="Read"))
    assert not provider.requests
    assert audit.events[-1].kind == "action.failed"


def test_attachment_budget_and_file_count(tmp_path, audit):
    (tmp_path / "large.txt").write_text("x" * 16001)
    wrapper = AttachmentRuntime(CapturingRuntime(), tmp_path, ("large.txt",), audit)
    with pytest.raises(InferenceError, match="16,000"):
        wrapper.prepare(AgentRequest(message="Read"))
    with pytest.raises(InferenceError, match="eight"):
        AttachmentRuntime(CapturingRuntime(), tmp_path, ("large.txt",) * 9, audit)


def test_provider_input_budget_includes_attachments(tmp_path, audit):
    (tmp_path / "note.txt").write_text("x" * 10000)
    prepared = AttachmentRuntime(CapturingRuntime(), tmp_path, ("note.txt",), audit).prepare(
        AgentRequest(message="Read")
    )
    runtime = OllamaAgentRuntime(
        load_identity(),
        InferenceSettings(provider="ollama", model="local:tag", max_context_characters=5000),
    )
    with pytest.raises(InferenceError, match="input size"):
        runtime.validate_request(prepared)


@pytest.mark.parametrize(
    "flags",
    [
        ["--attach", "note.txt"],
        ["--workspace", "."],
        ["--workspace", ".", "--attach", "note.txt"],
    ],
)
def test_cli_rejects_incomplete_or_mock_attachment_options(flags, capsys):
    assert main(["chat", *flags, "Read"]) == 1
    assert "ELARA:" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_saved_chat_persists_original_prompt_not_attachment(tmp_path):
    (tmp_path / "note.txt").write_text("private source text")
    store = SQLiteStore(tmp_path / "db" / "elara.sqlite3")
    session = store.create_session()
    provider = CapturingRuntime()
    wrapper = AttachmentRuntime(provider, tmp_path, ("note.txt",), store)
    result = await ConversationService(wrapper, store).respond(session.id, "Summarize")
    assert result.message == "A summary"
    assert provider.requests[0].attachments[0].content == "private source text"
    snapshot = store.snapshot(session.id)
    assert [turn.content for turn in snapshot.turns] == ["Summarize", "A summary"]
    assert len(store.audit_events(session.id)) == 3

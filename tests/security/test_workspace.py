import os
from pathlib import Path
from uuid import uuid4

import pytest

from elara.actions.gateway import ActionDenied, ActionGateway
from elara.actions.policy import ActionRequest, AuthorizationPolicy, Grant
from elara.actions.workspace import WorkspaceReader
from elara.api.workspace_cli import NoSyntheticAction
from elara.cli import main
from elara.core.settings import load_settings
from elara.memory.store import SQLiteStore


def test_read_and_list(tmp_path):
    (tmp_path / "notes.md").write_text("Hello ELARA", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    (tmp_path / ".private").write_text("secret")
    reader = WorkspaceReader(tmp_path)
    assert reader.read("notes.md") == "Hello ELARA"
    assert reader.list_files(".") == "folder/\nnotes.md"


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "folder/../../secret.txt",
        r"..\secret.txt",
        "/secret.txt",
        r"C:\secret.txt",
        "C:secret.txt",
        r"\\host\share\a.txt",
        "a.txt:secret",
        ".env",
        ".private/a.txt",
        "folder./a.txt",
        "folder /a.txt",
    ],
)
def test_rejects_unsafe_paths(tmp_path, path):
    with pytest.raises(PermissionError):
        WorkspaceReader(tmp_path).read(path)


@pytest.mark.parametrize("content", [b"x" * 65537, b"binary\x00", b"\xff"])
def test_rejects_non_text_or_oversized_files(tmp_path, content):
    (tmp_path / "notes.txt").write_bytes(content)
    with pytest.raises(ValueError):
        WorkspaceReader(tmp_path).read("notes.txt")


def test_rejects_hardlinks(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("private")
    try:
        os.link(source, tmp_path / "alias.txt")
    except PermissionError:
        pytest.skip("Host does not permit creating hardlinks")
    with pytest.raises(PermissionError):
        WorkspaceReader(tmp_path).read("alias.txt")


def test_multiple_links_rejected(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("private")
    reader = WorkspaceReader(tmp_path)
    original = Path.stat

    class LinkedInfo:
        st_mode = 0o100644
        st_nlink = 2

    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, **kwargs: (
            LinkedInfo()
            if path == source and kwargs.get("follow_symlinks", True)
            else original(path, **kwargs)
        ),
    )
    with pytest.raises(PermissionError):
        reader.read("source.txt")


def test_rejects_symlinks(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("private")
    try:
        (tmp_path / "alias.txt").symlink_to(source)
    except OSError:
        pytest.skip("Host does not permit creating symlinks")
    with pytest.raises(PermissionError):
        WorkspaceReader(tmp_path).read("alias.txt")


def test_reparse_point_rejected(tmp_path, monkeypatch):
    original = Path.lstat

    class ReparseInfo:
        st_mode = 0
        st_file_attributes = 0x400

    monkeypatch.setattr(
        Path, "lstat", lambda path: ReparseInfo() if path == tmp_path else original(path)
    )
    with pytest.raises(PermissionError):
        WorkspaceReader(tmp_path)


def test_directory_limit_includes_hidden_entries(tmp_path):
    for i in range(201):
        (tmp_path / f".hidden{i}").touch()
    with pytest.raises(ValueError):
        WorkspaceReader(tmp_path).list_files(".")


def test_denial_never_calls_workspace(tmp_path, audit, monkeypatch):
    reader = WorkspaceReader(tmp_path)

    def unexpected(resource):
        pytest.fail("Denied request reached filesystem adapter")

    monkeypatch.setattr(reader, "read", unexpected)
    grant = Grant(
        actor_id=uuid4(), session_id=uuid4(), capability="workspace.read", resource="notes.txt"
    )
    gateway = ActionGateway(
        AuthorizationPolicy((grant,)), NoSyntheticAction(), audit=audit, workspace=reader
    )
    for change in (
        {"actor_id": uuid4()},
        {"session_id": uuid4()},
        {"resource": "other.txt"},
        {"capability": "workspace.list"},
    ):
        with pytest.raises(ActionDenied):
            gateway.execute(ActionRequest(**(grant.model_dump() | change)))
    assert [event.kind for event in audit.events] == ["action.decision"] * 4


def test_cli_read_and_failed_read_are_audited(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("Hello ELARA", encoding="utf-8")
    for resource, expected_status, outcome in [
        ("notes.txt", 0, "action.succeeded"),
        ("../secret.txt", 1, "action.failed"),
    ]:
        assert main(["workspace", "--root", str(tmp_path), "read", resource]) == expected_status
        output = capsys.readouterr().out
        from uuid import UUID

        audit_id = UUID(output.splitlines()[0].split(": ")[1])
        events = SQLiteStore(load_settings().data_dir / "database" / "elara.sqlite3").audit_events(
            audit_id
        )
        assert [event.kind for event in events] == ["action.decision", "action.started", outcome]
        assert "Hello ELARA" not in " ".join(event.model_dump_json() for event in events)
        if expected_status == 0:
            assert "Hello ELARA" in output

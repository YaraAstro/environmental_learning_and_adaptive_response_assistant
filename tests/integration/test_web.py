import base64
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
from pydantic import ValidationError

from elara.api import web
from elara.api.memory_cli import interactive_command
from elara.api.web import ChatInput, authorized, create_app
from elara.core.contracts import AgentResponse, AttachedDocument, MemoryFact
from elara.core.identity import load_identity
from elara.core.inference import InferenceError
from elara.core.settings import InferenceSettings, Settings
from elara.memory.store import SQLiteStore


def test_ui_automatic_port_uses_bound_socket_and_matching_origin(tmp_path, monkeypatch, capsys):
    import uvicorn

    observed = {}

    def run(server, sockets):
        listener = sockets[0]
        port = listener.getsockname()[1]
        assert port > 0
        assert server.config.port == port
        observed["port"] = port
        observed["socket"] = listener

    monkeypatch.setattr(uvicorn.Server, "run", run)
    web.serve(Settings(data_dir=tmp_path), 0)
    assert f"127.0.0.1:{observed['port']}/#token=" in capsys.readouterr().out
    assert observed["socket"].fileno() == -1


def test_ui_bind_failure_does_not_print_launch_url(tmp_path, monkeypatch, capsys):
    class DeniedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            raise PermissionError(13, "Access denied")

    monkeypatch.setattr(web.socket, "socket", lambda *args: DeniedSocket())
    with pytest.raises(InferenceError, match="--port 0"):
        web.serve(Settings(data_dir=tmp_path), 8765)
    assert "Open ELARA" not in capsys.readouterr().out


def endpoint(app, path, method="GET"):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", "") == path and method in route.methods
    )


@pytest.mark.parametrize(
    "host,origin,auth,expected",
    [
        ("127.0.0.1:8765", None, "Bearer test-token", True),
        ("127.0.0.1:8765", "http://127.0.0.1:8765", "Bearer test-token", True),
        ("127.0.0.1:8765", "https://evil.example", "Bearer test-token", False),
        ("evil.example:8765", None, "Bearer test-token", False),
        ("127.0.0.1:8765", None, "", False),
        ("127.0.0.1:8765", None, "Bearer wrong", False),
        ("127.0.0.1:8765", "null", "Bearer test-token", False),
    ],
)
def test_ui_authorization(host, origin, auth, expected):
    assert authorized(host, origin, auth, "test-token", 8765) is expected


@pytest.mark.parametrize(
    "path,content",
    [
        ("../a.txt", "a"),
        (".env", "a"),
        ("image.png", "a"),
        ("a.txt", "x" * 16001),
        ("a.txt", "binary\x00"),
    ],
)
def test_browser_attachment_bounds(path, content):
    with pytest.raises(ValidationError):
        ChatInput(
            session_id=uuid4(),
            message="Read",
            attachments=(AttachedDocument(path=path, content=content),),
        )


def test_ui_routes_reuse_existing_sessions_and_memories(tmp_path):
    settings = Settings(data_dir=tmp_path)
    store = SQLiteStore(tmp_path / "database" / "elara.sqlite3")
    session = store.create_session()
    store.append_exchange(
        session.id, "Hello from the CLI", "Hello", simulated=True, expected_revision=0
    )
    app = create_app(settings, "test-token")
    assert endpoint(app, "/api/sessions")()[0]["title"] == "Hello from the CLI"
    assert len(endpoint(app, "/api/sessions/{session_id}")(session.id)["turns"]) == 2
    endpoint(app, "/api/memories", "PUT")(MemoryFact(key="name", value="Yara"))
    assert store.memories()[0].value == "Yara"
    endpoint(app, "/api/memories/{key}", "DELETE")("name")
    assert not store.memories()
    endpoint(app, "/api/sessions/{session_id}", "DELETE")(session.id)
    assert not store.list_sessions()


def test_ui_assets_and_identity_are_packaged(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), "test-token")
    html = endpoint(app, "/")().body.decode()
    js = endpoint(app, "/app.js")().body.decode()
    assert "ELARA" in html and 'id="root"' in html
    assert "/app.js" in html and "/style.css" in html
    assert "memory-form" in js
    assert "test-token" not in html + js
    assert "You are ELARA" in load_identity().instructions()
    assert "distinguish it honestly" in load_identity().instructions()


def test_quoted_memory_and_singular_alias(tmp_path, capsys):
    path = tmp_path / "elara.sqlite3"
    interactive_command('/remember name="Yara"', path)
    assert SQLiteStore(path).memories()[0].value == "Yara"
    assert interactive_command("/memory", path)
    assert "Yara" in capsys.readouterr().out


class FakeRuntime:
    def __init__(self):
        self.requests = []
        self.fail = False

    async def respond(self, request):
        self.requests.append(request)
        if self.fail:
            raise InferenceError("Test provider unavailable")
        return AgentResponse(message="Hello Yara", session_id=request.session_id, simulated=False)


@pytest.mark.asyncio
async def test_http_chat_auth_memory_attachment_and_failed_turn(tmp_path, monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setattr(web, "build_runtime", lambda settings: runtime)
    app = create_app(
        Settings(
            data_dir=tmp_path, inference=InferenceSettings(provider="ollama", model="local:test")
        ),
        "test-token",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as client:
        assert (await client.get("/api/sessions")).status_code == 401
        client.headers["Authorization"] = "Bearer test-token"
        assert (
            await client.get("/api/sessions", headers={"Origin": "https://evil.example"})
        ).status_code == 403
        index = await client.get("/")
        assert "frame-ancestors 'none'" in index.headers["Content-Security-Policy"]
        session = (await client.post("/api/sessions")).json()
        assert (
            await client.put("/api/memories", json={"key": "name", "value": "Yara"})
        ).status_code == 200
        body = {
            "session_id": session["id"],
            "message": "Hi",
            "attachments": [{"path": "a.txt", "content": "note"}],
            "media": [
                {
                    "name": "frame.png",
                    "mime_type": "image/png",
                    "source": "image",
                    "data": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"fixture").decode(),
                }
            ],
        }
        reply = await client.post("/api/chat", json=body)
        assert reply.status_code == 200 and reply.json()["message"] == "Hello Yara"
        assert runtime.requests[-1].memories[0].value == "Yara"
        assert runtime.requests[-1].attachments[0].content == "note"
        assert runtime.requests[-1].media[0].name == "frame.png"
        runtime.fail = True
        assert (await client.post("/api/chat", json=body | {"recall": False})).status_code == 502
        assert not runtime.requests[-1].memories
        store = SQLiteStore(tmp_path / "database" / "elara.sqlite3")
        assert len(store.snapshot(UUID(session["id"])).turns) == 2
        saved = await client.get(f"/api/sessions/{session['id']}")
        assert body["media"][0]["data"] not in saved.text
        invalid = await client.post(
            "/api/chat", json=body | {"media": [body["media"][0] | {"source": "audio"}]}
        )
        assert invalid.status_code == 422
        assert body["media"][0]["data"] not in invalid.text
        assert (await client.post("/api/chat", content=b"x" * 17_000_001)).status_code == 413
        assert (await client.put("/api/memories", content=b"x" * 300_001)).status_code == 413
